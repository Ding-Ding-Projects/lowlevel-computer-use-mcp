const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
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
const appendJson = (name, value, limit = 200) => {
  const entries = readJson(name, []);
  entries.unshift(value);
  writeJson(name, entries.slice(0, limit));
  return entries[0];
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
  if (!sync.ok) return { ok: false, stage: 'uv-sync', output: sync.stderr || sync.stdout };
  if (process.platform !== 'win32') return { ok: true, stage: 'complete', output: sync.stdout };
  const ahkProbe = await runHidden('where.exe', ['AutoHotkey64.exe']);
  if (!ahkProbe.ok) {
    const winget = await runHidden('winget.exe', [
      'install', '--exact', '--id', 'AutoHotkey.AutoHotkey', '--silent',
      '--accept-source-agreements', '--accept-package-agreements'
    ]);
    return { ok: winget.ok, stage: 'autohotkey', output: winget.stderr || winget.stdout };
  }
  return { ok: true, stage: 'complete', output: sync.stdout };
}

async function remoteCall(baseUrl, tool, input) {
  let endpoint;
  try {
    const parsed = new URL(baseUrl);
    if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Only HTTP(S) API URLs are supported.');
    endpoint = new URL('/api/execute', parsed).toString();
  } catch (error) {
    return { ok: false, error: String(error) };
  }
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ tool, arguments: input || {} }), signal: controller.signal
    });
    clearTimeout(timeout);
    const payload = await response.json();
    return response.ok ? payload : { ok: false, ...payload, status: response.status };
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

async function getToolCatalog() {
  const probeSpec = commandSpec();
  const probe = await runHidden(probeSpec.file, [...probeSpec.prefix, 'list_headless_desktops', '--json', '{}']);
  return {
    ok: true,
    serverReady: probe.ok || Boolean(probe.stdout),
    tools: [
      'ahk_control_send', 'ahk_status', 'close_headless_desktop',
      'create_headless_desktop', 'create_headless_desktops', 'create_virtual_display',
      'crop_image', 'download_file', 'get_active_window', 'get_cursor_position',
      'get_screen_size', 'hide_headless_desktop', 'hide_window', 'install_startup',
      'is_admin', 'kill_process', 'launch_on_headless_desktop', 'launch_on_virtual_display',
      'linux_status', 'list_child_windows', 'list_headless_desktops', 'list_headless_windows',
      'list_processes', 'list_virtual_display_windows', 'list_windows', 'mouse_click',
      'mouse_drag', 'mouse_move', 'mouse_scroll', 'move_window', 'press_keys',
      'recording_status', 'resize_window', 'run_ahk', 'run_command', 'run_command_as_admin',
      'screenshot', 'screenshot_virtual_display', 'show_headless_desktop', 'show_window',
      'start_screen_recording', 'startup_status', 'stop_screen_recording',
      'stop_virtual_display', 'type_text', 'uninstall_startup', 'upload_file',
      'win_send_keys', 'win_set_control_text', 'window_action', 'wsl_create_temp',
      'wsl_destroy', 'wsl_destroy_all_temp', 'wsl_list_distros', 'wsl_list_temp',
      'wsl_run', 'wsl_status'
    ]
  };
}

async function getChangelog() {
  const result = await runHidden(process.platform === 'win32' ? 'git.exe' : 'git', ['-C', repoDir, 'log', '--all', '--date=short', '--format=%H%x1f%ad%x1f%s%x1f%b%x1e']);
  if (!result.ok) return { ok: false, error: result.stderr || result.stdout };
  const entries = result.stdout.split('\x1e').map((record) => record.trim()).filter(Boolean).map((record) => {
    const [commit, date, subject, body = ''] = record.split('\x1f');
    return { commit, date, subject, body: body.trim() };
  }).filter((entry) => entry.commit && entry.subject);
  return { ok: true, entries };
}

async function startApi(host, port) {
  if (apiProcess && apiProcess.exitCode === null) return { ok: true, running: true, ready: true, host, port };
  const spec = serverSpec(host, port);
  try {
    apiProcess = spawn(spec.file, spec.args, { cwd: repoDir, shell: false, windowsHide: true, stdio: ['ignore', 'ignore', 'ignore'] });
    apiProcess.on('exit', () => { apiProcess = null; });
    await new Promise((resolve, reject) => { apiProcess.once('spawn', resolve); apiProcess.once('error', reject); });
    const health = `http://${host === '0.0.0.0' ? '127.0.0.1' : host}:${port}/health`;
    let lastError = '';
    for (let attempt = 0; attempt < 30; attempt += 1) {
      try {
        const response = await fetch(health);
        if (response.ok) return { ok: true, running: true, ready: true, host, port, mcp: `http://${host}:${port}/mcp`, health };
        lastError = `HTTP ${response.status}`;
      } catch (error) { lastError = String(error); }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    stopApi();
    return { ok: false, running: false, error: `API did not become ready: ${lastError}` };
  } catch (error) {
    apiProcess = null;
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
  const file = process.platform === 'win32' ? 'uv.exe' : 'uv';
  const args = ['run', '--directory', repoDir, 'lowlevel-computer-use-mcp', action];
  if (action === 'install-startup') {
    args.push('--host', host, '--port', String(port));
    if (!admin) args.push('--no-admin');
  }
  return runHidden(file, args);
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

async function captureScreenshots(outputDir) {
  fs.mkdirSync(outputDir, { recursive: true });
  const win = new BrowserWindow({
    width: 1440, height: 1000, show: false, offscreen: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false }
  });
  await win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  await new Promise((resolve) => setTimeout(resolve, 1800));
  const captures = [
    ['electron-workspaces.png', 'workspace'],
    ['electron-settings.png', 'settings'],
    ['electron-tab-management.png', 'settings-tabs'],
    ['electron-changelog.png', 'changelog']
  ];
  for (const [filename, tab] of captures) {
    await win.webContents.executeJavaScript(`window.__captureTab(${JSON.stringify(tab)})`);
    await new Promise((resolve) => setTimeout(resolve, 250));
    const image = await win.webContents.capturePage();
    fs.writeFileSync(path.join(outputDir, filename), image.toPNG());
  }
  win.destroy();
  app.quit();
}

app.whenReady().then(() => {
  ipcMain.handle('tool:run', (_event, name, input) => runTool(name, input));
  ipcMain.handle('bootstrap', () => bootstrap());
  ipcMain.handle('remote:call', (_event, baseUrl, tool, input) => remoteCall(baseUrl, tool, input));
  ipcMain.handle('connections:get', () => readJson('connections.json', []));
  ipcMain.handle('connections:set', (_event, connections) => { writeJson('connections.json', connections); return connections; });
  ipcMain.handle('agents:get', () => readJson('agents.json', []));
  ipcMain.handle('agents:set', (_event, agents) => { writeJson('agents.json', agents); return agents; });
  ipcMain.handle('tools:list', () => getToolCatalog());
  ipcMain.handle('changelog:get', () => getChangelog());
  ipcMain.handle('release:codename', () => { try { return JSON.parse(fs.readFileSync(path.join(__dirname, 'release-codename.json'), 'utf8')); } catch { return { codeName: 'Unassigned build' }; } });
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
  ipcMain.handle('notifications:get', () => readJson('notifications.json', []));
  ipcMain.handle('notifications:add', (_event, notification) => appendJson('notifications.json', notification, 300));
  ipcMain.handle('notifications:clear', () => { writeJson('notifications.json', []); return []; });
  ipcMain.handle('tabs:get', () => readJson('tabs.json', {
    order: ['workspace', 'runner', 'history', 'settings', 'notifications', 'changelog', 'help'],
    pinned: ['workspace'],
    groups: { core: { label: 'Core', collapsed: false, tabs: ['workspace', 'runner'] }, records: { label: 'Records', collapsed: false, tabs: ['history', 'notifications', 'changelog'] }, customize: { label: 'Customize', collapsed: false, tabs: ['settings', 'help'] } }
  }));
  ipcMain.handle('tabs:set', (_event, tabs) => { writeJson('tabs.json', tabs); return tabs; });
  ipcMain.handle('export:text', (_event, text) => {
    const file = path.join(app.getPath('downloads'), `lowlevel-manual-${Date.now()}.md`);
    fs.writeFileSync(file, text, 'utf8');
    return file;
  });
  ipcMain.handle('open:external', (_event, url) => {
    const parsed = new URL(url);
    if (!['https:', 'http:'].includes(parsed.protocol)) throw new Error('Only web links can be opened.');
    return shell.openExternal(parsed.toString());
  });
  ipcMain.handle('browse:path', async (event, kind) => {
    const owner = BrowserWindow.fromWebContents(event.sender);
    const properties = kind === 'folder' ? ['openDirectory', 'createDirectory'] : ['openFile'];
    const filters = kind === 'app' ? [{ name: 'Applications', extensions: ['exe', 'com', 'bat', 'cmd'] }] : undefined;
    const result = await dialog.showOpenDialog(owner, { properties, filters, title: kind === 'app' ? 'Choose an application to launch invisibly' : kind === 'folder' ? 'Choose a folder' : 'Choose a file' });
    return result.canceled ? null : result.filePaths[0];
  });
  const captureArgument = process.argv.find((argument) => argument.startsWith('--capture-dir='));
  if (captureArgument) captureScreenshots(path.resolve(captureArgument.slice('--capture-dir='.length)));
  else createWindow();
  if (process.platform === 'win32') bootstrap();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { stopApi(); if (process.platform !== 'darwin') app.quit(); });
