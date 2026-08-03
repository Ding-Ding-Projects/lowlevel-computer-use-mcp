const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const repoDir = path.resolve(__dirname, '..');
let apiProcess = null;
const stateDir = () => app.getPath('userData');
const readJson = (name, fallback) => {
  try { return JSON.parse(fs.readFileSync(path.join(stateDir(), name), 'utf8')); }
  catch { return fallback; }
};
const writeJson = (name, value) => {
  fs.mkdirSync(stateDir(), { recursive: true });
  fs.writeFileSync(path.join(stateDir(), name), JSON.stringify(value, null, 2));
};

function commandSpec() {
  if (process.platform === 'win32') return { file: 'uv.exe', prefix: ['run', '--directory', repoDir, 'lowlevel-computer-use-cheap'] };
  return { file: 'uv', prefix: ['run', '--directory', repoDir, 'lowlevel-computer-use-cheap'] };
}

function serverSpec(host, port) {
  const file = commandSpec().file;
  return { file, args: ['run', '--directory', repoDir, 'lowlevel-computer-use-mcp', '--http', '--host', host, '--port', String(port)] };
}

function runHidden(file, args, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(file, args, {
      cwd: options.cwd || repoDir,
      shell: false,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });
    let stdout = '', stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    child.on('error', (error) => resolve({ ok: false, returncode: -1, stdout, stderr: String(error) }));
    child.on('close', (returncode) => resolve({ ok: returncode === 0, returncode, stdout, stderr }));
  });
}

async function runTool(name, input) {
  const spec = commandSpec();
  const result = await runHidden(spec.file, [...spec.prefix, name, '--json', JSON.stringify(input || {})]);
  let parsed;
  try { parsed = JSON.parse(result.stdout); } catch { parsed = { ok: result.ok, output: result.stdout, error: result.stderr }; }
  const history = readJson('history.json', []);
  history.unshift({ at: new Date().toISOString(), tool: name, input: input || {}, result: parsed });
  writeJson('history.json', history.slice(0, 200));
  return parsed;
}

async function bootstrap() {
  const uv = commandSpec().file;
  const probe = await runHidden(uv, ['--version']);
  if (!probe.ok) {
    const pip = process.platform === 'win32' ? 'python.exe' : 'python3';
    const installed = await runHidden(pip, ['-m', 'pip', 'install', '--user', 'uv']);
    if (!installed.ok) return { ok: false, stage: 'uv', output: installed.stderr || installed.stdout };
  }
  const sync = await runHidden(uv, ['sync'], { cwd: repoDir });
  return { ok: sync.ok, stage: 'uv-sync', output: sync.stderr || sync.stdout };
}

async function remoteCall(baseUrl, tool, input) {
  const endpoint = new URL('/api/execute', baseUrl).toString();
  try {
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ tool, arguments: input || {} })
    });
    return await response.json();
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

function startApi(host, port) {
  if (apiProcess && apiProcess.exitCode === null) return { ok: true, running: true, host, port };
  const spec = serverSpec(host, port);
  try {
    apiProcess = spawn(spec.file, spec.args, { cwd: repoDir, shell: false, windowsHide: true, stdio: ['ignore', 'ignore', 'ignore'] });
    apiProcess.on('exit', () => { apiProcess = null; });
    return { ok: true, running: true, host, port, mcp: `http://${host}:${port}/mcp`, health: `http://${host}:${port}/health` };
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

function stopApi() {
  if (!apiProcess || apiProcess.exitCode !== null) { apiProcess = null; return { ok: true, running: false }; }
  apiProcess.kill();
  apiProcess = null;
  return { ok: true, running: false };
}

async function startupAction(action, host, port, admin = false) {
  const spec = commandSpec();
  const args = [...spec.prefix.slice(0, 3), 'lowlevel-computer-use-mcp', action];
  if (action === 'install-startup') {
    args.push('--host', host, '--port', String(port));
    if (!admin) args.push('--no-admin');
  }
  return runHidden(spec.file, args);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280, height: 860, minWidth: 900, minHeight: 620,
    title: 'Low-Level Computer-Use Manual',
    show: false,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false }
  });
  win.once('ready-to-show', () => win.show());
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(() => {
  ipcMain.handle('tool:run', (_event, name, input) => runTool(name, input));
  ipcMain.handle('bootstrap', () => bootstrap());
  ipcMain.handle('remote:call', (_event, baseUrl, tool, input) => remoteCall(baseUrl, tool, input));
  ipcMain.handle('connections:get', () => readJson('connections.json', []));
  ipcMain.handle('connections:set', (_event, connections) => { writeJson('connections.json', connections); return connections; });
  ipcMain.handle('api:start', (_event, host, port) => startApi(host, port));
  ipcMain.handle('api:stop', () => stopApi());
  ipcMain.handle('api:status', () => ({ running: Boolean(apiProcess && apiProcess.exitCode === null) }));
  ipcMain.handle('startup:install', (_event, host, port, admin) => startupAction('install-startup', host, port, admin));
  ipcMain.handle('startup:remove', () => startupAction('uninstall-startup', '127.0.0.1', 8765, false));
  ipcMain.handle('startup:status', () => startupAction('startup-status', '127.0.0.1', 8765, false));
  ipcMain.handle('settings:get', () => readJson('settings.json', {
    language: 'English', englishFunny: 1, cantoneseFunny: 1, theme: 'dark', density: 'comfortable', accent: '#8ab4f8', fontScale: 1
  }));
  ipcMain.handle('settings:set', (_event, settings) => { writeJson('settings.json', settings); return settings; });
  ipcMain.handle('history:get', () => readJson('history.json', []));
  ipcMain.handle('export:text', (_event, text) => {
    const file = path.join(app.getPath('downloads'), `lowlevel-manual-${Date.now()}.md`);
    fs.writeFileSync(file, text, 'utf8');
    return file;
  });
  ipcMain.handle('open:external', (_event, url) => shell.openExternal(url));
  createWindow();
  if (process.platform === 'win32') bootstrap();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { stopApi(); if (process.platform !== 'darwin') app.quit(); });
