const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const binary = process.platform === 'win32'
  ? path.join(__dirname, 'node_modules', 'electron', 'dist', 'electron.exe')
  : path.join(__dirname, 'node_modules', 'electron', 'dist', 'electron');
const electronPackage = path.join(__dirname, 'node_modules', 'electron', 'package.json');
if (!fs.existsSync(electronPackage)) {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const install = spawnSync(npm, ['install'], { cwd: __dirname, windowsHide: true, stdio: 'ignore' });
  if (install.error || install.status !== 0 || !fs.existsSync(electronPackage)) {
    console.error(`Electron dependencies could not be installed: ${install.error?.message || `exit ${install.status}`}`);
    process.exit(1);
  }
}
if (!fs.existsSync(binary)) {
  const installer = path.join(__dirname, 'node_modules', 'electron', 'install.js');
  const result = spawnSync(process.execPath, [installer], { cwd: __dirname, windowsHide: true, stdio: 'ignore' });
  if (result.error || result.status !== 0 || !fs.existsSync(binary)) {
    console.error(`Electron runtime installation failed: ${result.error?.message || `exit ${result.status}`}`);
    process.exit(1);
  }
}
const child = spawn(binary, ['.', ...process.argv.slice(2)], {
  cwd: __dirname,
  shell: false,
  windowsHide: true,
  stdio: 'inherit'
});
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
child.on('error', (error) => { console.error(`Electron binary could not start: ${error.message}`); process.exit(1); });
