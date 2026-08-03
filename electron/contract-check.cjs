const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = __dirname;
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const main = read('main.cjs');
const renderer = read('renderer/app.js');
const html = read('renderer/index.html');
const launcher = read('launch.cjs');
const packageJson = JSON.parse(read('package.json'));

assert.match(main, /windowsHide:\s*true/);
assert.match(main, /shell:\s*false/);
assert.match(main, /'lowlevel-computer-use-mcp', action/);
assert.doesNotMatch(main, /prefix\.slice\(0, 3\)/);
assert.match(main, /git', \['-C', repoDir, 'log', '--all'/);
assert.match(main, /AbortController/);
assert.match(launcher, /npm\.cmd/);
assert.match(launcher, /install/);
assert.match(launcher, /install\.js/);
assert.match(renderer, /ensureQuickLaunchBrowser/);
assert.match(renderer, /browseQuickLaunchApp/);
assert.match(renderer, /openTabRegex/);
assert.match(renderer, /updateTabRegex/);
assert.match(renderer, /toolCatalogNames/);
for (const id of ['launchCommand', 'tabRegexPanel', 'commandPalette', 'confirmDialog']) assert.match(html, new RegExp(`id="${id}"`));
assert.equal(packageJson.build.win.target[0].target, 'squirrel');
for (const screenshot of ['electron-workspaces.png', 'electron-settings.png', 'electron-changelog.png']) {
  const screenshotPath = path.join(root, '..', 'docs', 'screenshots', screenshot);
  assert.ok(fs.existsSync(screenshotPath) && fs.statSync(screenshotPath).size > 1000, `missing screenshot: ${screenshot}`);
}
console.log('Electron contract checks passed.');
