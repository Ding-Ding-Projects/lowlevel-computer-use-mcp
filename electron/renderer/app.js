const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const DEFAULT_SETTINGS = { language: 'English', englishFunny: 1, cantoneseFunny: 1, theme: 'dark', density: 'comfortable', accent: '#8ab4f8', fontScale: 1, appearance: { font: 'Segoe UI', weight: 400, radius: 20, surface: '#1a1d24', text: '#e4e1e9', accent: '#aec6ff' } };
const DEFAULT_TABS = { order: ['workspace', 'runner', 'history', 'settings', 'notifications', 'changelog', 'help', 'memory'], pinned: ['workspace'], groups: { core: { label: 'Core', collapsed: false, tabs: ['workspace', 'runner'] }, records: { label: 'Records', collapsed: false, tabs: ['history', 'notifications', 'changelog'] }, customize: { label: 'Customize', collapsed: false, tabs: ['settings', 'help', 'memory'] } } };
const TAB_LABELS = { workspace: 'Workspaces', runner: 'Tool runner', history: 'History', settings: 'Settings', notifications: 'Notifications', changelog: 'Changelog', help: 'Manual', memory: 'Memory' };
const DOCS_URL = 'https://codingmachineedge.github.io/lowlevel-computer-use-mcp/';
const CHANGELOG = [{ version: '0.1.0', date: '2026-08-03', title: 'Headless-first remote control foundation', codeName: 'Classic Har Gow · 蝦餃', codeNameUrl: 'https://github.com/Ding-Ding-Projects/dim-sum-photos/releases/download/catalog-v1/hk-dish-0001-classic-har-gow.png', commit: '92d5fda64a9db8e65ab2cf39b094408fb8eab634', url: 'https://github.com/codingmachineedge/lowlevel-computer-use-mcp/commit/92d5fda64a9db8e65ab2cf39b094408fb8eab634', changes: ['Multiple named headless desktops for project and agent isolation.', 'Console-free process launch and foreground focus protection.', 'Trusted-LAN API with command execution and bounded file transfer.', 'Electron manual client with saved connections, history, settings, and regex search.'] }];

let settings = { ...DEFAULT_SETTINGS, appearance: { ...DEFAULT_SETTINGS.appearance } };
let tabs = JSON.parse(JSON.stringify(DEFAULT_TABS));
let connections = [];
let agents = [];
let notifications = [];
let desktops = [];
let changelogEntries = CHANGELOG;
let memoryEntries = [];
let toolCatalogNames = [];
let activeTab = 'workspace';
let appearanceTarget = 'global';
let contextTab = null;
const regexStates = {};
const bulkTabState = { pattern: '', flags: 'i' };

const funnyTail = (level, english, cantonese) => {
  if (level <= 1) return { english, cantonese };
  if (level === 2) return { english: `${english} — quietly sorted.`, cantonese: `${cantonese}，靜靜搞掂。` };
  if (level === 3) return { english: `${english} — the pixels behaved.`, cantonese: `${cantonese}，啲 pixels 今次幾合作。` };
  if (level === 4) return { english: `${english} — no terminal window escaped.`, cantonese: `${cantonese}，今次冇 terminal 偷走出嚟。` };
  return { english: `${english} — the desktop stayed yours while the tiny robot did its chores.`, cantonese: `${cantonese}，個 desktop 留返畀你，細機械人自己做嘢。` };
};
function localized(english, cantonese) {
  const tone = funnyTail(Number(settings.language === 'Playful Hong Kong Cantonese' ? settings.cantoneseFunny : settings.englishFunny), english, cantonese);
  if (settings.language === 'Playful Hong Kong Cantonese') return tone.cantonese;
  if (settings.language === 'Bilingual') return `${tone.english} · ${tone.cantonese}`;
  return tone.english;
}
function show(message) { $('snackbar').textContent = message; $('snackbar').classList.add('show'); window.clearTimeout(show.timer); show.timer = window.setTimeout(() => $('snackbar').classList.remove('show'), 4200); }
async function notify(english, cantonese, level = 'info') { const text = localized(english, cantonese); show(text); const entry = { at: new Date().toISOString(), english, cantonese, text, level }; notifications.unshift(entry); notifications = notifications.slice(0, 300); renderNotifications(); try { await window.lowlevel.addNotification(entry); } catch { /* notification history must not break the requested operation */ } }
function setStatus(text) { $('statusText').textContent = text; }
function json(id) { try { return JSON.parse($(id).value || '{}'); } catch (error) { throw new Error(`JSON parameters are invalid: ${error.message}`); } }
function pageTitle(id) { return TAB_LABELS[id] || id; }
function normalizeTabs(value) { const valid = DEFAULT_TABS.order; const order = [...new Set((value?.order || []).filter((id) => valid.includes(id)))]; valid.forEach((id) => { if (!order.includes(id)) order.push(id); }); const source = value?.groups || DEFAULT_TABS.groups; const groups = {}; Object.entries(source).forEach(([id, group]) => { const cleanId = String(id).replace(/[^A-Za-z0-9_-]/g, '-'); if (!cleanId || groups[cleanId]) return; groups[cleanId] = { label: String(group?.label || cleanId), collapsed: Boolean(group?.collapsed), tabs: [...new Set((group?.tabs || []).filter((tabId) => order.includes(tabId)))] }; }); if (!Object.keys(groups).length) Object.assign(groups, JSON.parse(JSON.stringify(DEFAULT_TABS.groups))); return { order, pinned: [...new Set((value?.pinned || []).filter((id) => valid.includes(id)))], groups }; }

async function run(name, input) {
  setStatus(localized(`Running ${name}…`, `行緊 ${name}…`));
  try {
    const target = $('targetConnection')?.value || 'local';
    const connection = connections.find((item) => item.id === target);
    const result = connection ? await window.lowlevel.remoteCall(connection.url, name, input) : await window.lowlevel.runTool(name, input);
    setStatus(result?.ok ? localized('Ready', '準備好喇') : localized('Needs attention', '要睇睇喇'));
    $('toolOutput').textContent = JSON.stringify(result, null, 2);
    return result;
  } catch (error) {
    setStatus(localized('Needs attention', '要睇睇喇'));
    $('toolOutput').textContent = error.stack || error.message;
    await notify('The tool call failed.', '個工具呼叫失敗喇。', 'error');
    return { ok: false, error: error.message };
  }
}

function groupForTab(id) { return Object.entries(tabs.groups).find(([, group]) => group.tabs.includes(id)); }
function removeTabFromGroups(id) { Object.values(tabs.groups).forEach((group) => { group.tabs = group.tabs.filter((tabId) => tabId !== id); }); }
function renderTabGroupOptions() {
  const select = $('tabGroupSelect');
  const scope = $('tabBulkScope');
  if (!select || !scope) return;
  const options = Object.entries(tabs.groups).map(([id, group]) => `<option value="${escapeHtml(id)}">${escapeHtml(group.label)}</option>`).join('');
  const selected = select.value;
  select.innerHTML = options;
  if (tabs.groups[selected]) select.value = selected;
  scope.innerHTML = `<option value="all">All open tabs</option>${options}`;
  if (scope.dataset.selected && (scope.dataset.selected === 'all' || tabs.groups[scope.dataset.selected])) scope.value = scope.dataset.selected;
}
function renderTabs() {
  const stripQuery = $('stripSearch')?.value || '';
  const matcher = makeMatcher('stripSearch', stripQuery);
  const order = [...tabs.pinned.filter((id) => tabs.order.includes(id)), ...tabs.order.filter((id) => !tabs.pinned.includes(id))];
  document.querySelector('.tabs').innerHTML = order.filter((id) => matcher(TAB_LABELS[id])).map((id) => `<button class="tab ${id === activeTab ? 'active' : ''}" data-tab="${id}" role="tab" aria-selected="${id === activeTab}" aria-label="${escapeHtml(TAB_LABELS[id])}${tabs.pinned.includes(id) ? ', pinned' : ''}">${escapeHtml(TAB_LABELS[id])}${tabs.pinned.includes(id) ? ' ·' : ''}</button>`).join('');
  document.querySelectorAll('.tab').forEach((tab) => {
    tab.draggable = true;
    tab.addEventListener('click', () => navigate(tab.dataset.tab));
    tab.addEventListener('keydown', (event) => { if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) { event.preventDefault(); openTabContextMenu(event, tab.dataset.tab); } });
    tab.addEventListener('dragstart', (event) => event.dataTransfer.setData('text/tab-id', tab.dataset.tab));
    tab.addEventListener('dragover', (event) => event.preventDefault());
    tab.addEventListener('drop', async (event) => { event.preventDefault(); moveTab(event.dataTransfer.getData('text/tab-id'), tab.dataset.tab); });
    tab.addEventListener('contextmenu', (event) => { event.preventDefault(); if (event.shiftKey) openAppearance(tab, tab.dataset.tab); else openTabContextMenu(event, tab.dataset.tab); });
  });
}
async function saveTabs() { tabs = normalizeTabs(tabs); await window.lowlevel.setTabs(tabs); renderTabs(); renderTabManager(); renderTabGroupOptions(); }
async function moveTab(from, to) { if (!from || !to || from === to) return; const order = tabs.order.filter((id) => id !== from); order.splice(Math.max(0, order.indexOf(to)), 0, from); tabs.order = order; await saveTabs(); }
async function navigate(id) { if (!TAB_LABELS[id]) return; activeTab = id; document.querySelectorAll('.page').forEach((page) => page.classList.toggle('active', page.id === id)); renderTabs(); if (id === 'history') await loadHistory(); if (id === 'notifications') await loadNotifications(); if (id === 'changelog') renderChangelog(); if (id === 'settings') renderTabManager(); if (id === 'memory') await loadMemory(); }

function makeMatcher(field, query) {
  const state = regexStates[field] || { pattern: '', flags: 'i' };
  if (state.pattern) { try { return (value) => { const expression = new RegExp(state.pattern, state.flags || 'i'); return expression.test(String(value)); }; } catch { return () => false; } }
  const lowered = String(query || '').toLocaleLowerCase();
  return (value) => String(value).toLocaleLowerCase().includes(lowered);
}
function wireRegexToggle(toggleId, panelId) { $(toggleId).addEventListener('click', () => $(panelId).classList.toggle('open')); }
function wireRegexInputs(field, patternId, flagsId, resultId, onChange) { regexStates[field] = { pattern: '', flags: 'i' }; const update = () => { regexStates[field] = { pattern: $(patternId).value, flags: $(flagsId).value || 'i' }; try { new RegExp(regexStates[field].pattern || '.', regexStates[field].flags); $(resultId).textContent = regexStates[field].pattern ? 'Valid regex; this mode is active.' : 'Plain text is the default. Regex is opt-in.'; } catch (error) { $(resultId).textContent = `Invalid regex: ${error.message}`; } onChange?.(); }; $(patternId).addEventListener('input', update); $(flagsId).addEventListener('input', update); }
function openTabRegex(target) { regexStates.activeTabField = target; const state = regexStates[target] || { pattern: '', flags: 'i' }; $('tabRegexPattern').value = state.pattern; $('tabRegexFlags').value = state.flags; $('tabRegexResult').textContent = state.pattern ? `Regex builder attached to ${target}.` : `Plain text is active for ${target}.`; $('tabRegexPanel').classList.add('open'); $('tabRegexPattern').focus(); }
function updateTabRegex() { const target = regexStates.activeTabField || 'stripSearch'; regexStates[target] = { pattern: $('tabRegexPattern').value, flags: $('tabRegexFlags').value || 'i' }; try { new RegExp(regexStates[target].pattern || '.', regexStates[target].flags); $('tabRegexResult').textContent = regexStates[target].pattern ? `Valid regex active for ${target}.` : `Plain text is active for ${target}.`; } catch (error) { $('tabRegexResult').textContent = `Invalid regex for ${target}: ${error.message}`; } renderTabs(); renderTabManager(); }

async function refreshDesktops() { const result = await run('list_headless_desktops', {}); desktops = result.desktops || []; $('desktopList').innerHTML = desktops.length ? desktops.map((d) => `<div class="history-item"><strong>${escapeHtml(d.name)}</strong><br><span class="support">${escapeHtml(d.window_count)} window(s) · ${escapeHtml(d.full)}</span></div>`).join('') : '<p class="empty">No desktops owned by this server process.</p>'; $('desktopSelect').innerHTML = desktops.length ? desktops.map((d) => `<option value="${escapeHtml(d.name)}">${escapeHtml(d.name)}</option>`).join('') : '<option>No desktops</option>'; }
async function loadConnections() { connections = await window.lowlevel.getConnections(); const options = ['<option value="local">Local cheap tools</option>', ...connections.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} · ${escapeHtml(item.url)}</option>`)].join(''); $('remoteSelect').innerHTML = options; $('targetConnection').innerHTML = options; }
async function loadTools() { const catalog = await window.lowlevel.getTools(); toolCatalogNames = catalog.tools || []; $('toolCatalog').innerHTML = toolCatalogNames.map((name) => `<option value="${escapeHtml(name)}"></option>`).join(''); }
function renderAgents() { const list = $('agentList'); if (!list) return; list.innerHTML = agents.length ? agents.map((agent) => `<article class="history-item"><strong>${escapeHtml(agent.name)}</strong><span class="support">${escapeHtml(agent.project)} · ${escapeHtml(agent.prefix)} · ${escapeHtml(agent.status)}</span></article>`).join('') : '<p class="empty">No subagent lanes saved yet.</p>'; }
async function loadAgents() { agents = await window.lowlevel.getAgents(); renderAgents(); }
async function createAgentLane() { const project = $('subagentProject').value.trim(); const name = $('subagentName').value.trim(); const count = Math.max(1, Math.min(32, Number($('subagentCount').value) || 1)); if (!project || !name) { await notify('Project and subagent names are required.', '要填 project 同 subagent 名。', 'error'); return; } const prefix = `${project}-${name}`.replace(/[^A-Za-z0-9_-]/g, '-'); const result = await run('create_headless_desktops', { count, prefix }); if (!result.ok) return; const agent = { id: `${Date.now()}`, project, name, prefix, desktopCount: count, status: 'ready', createdAt: new Date().toISOString() }; agents = [agent, ...agents]; await window.lowlevel.setAgents(agents); renderAgents(); await notify(`Subagent lane ${name} is ready.`, `Subagent lane ${name} 開好喇。`); }
function ensurePathBrowser() { if ($('browseLaunchApp')) return; const card = document.createElement('article'); card.className = 'path-browser-card card'; card.innerHTML = '<h3>Path browser</h3><p class="support">Choose an application, file, or folder and place its path into the launch or tool JSON field.</p><div class="inline-form"><button class="tonal" id="browseLaunchApp" type="button">Choose app for launch</button><button class="tonal" id="browseToolFile" type="button">Choose file</button><button class="tonal" id="browseToolFolder" type="button">Choose folder</button></div>'; $('runner').appendChild(card); }
function ensureQuickLaunchBrowser() { if ($('browseQuickLaunchApp')) return; const input = $('launchCommand'); if (!input?.parentElement) return; const wrapper = document.createElement('span'); wrapper.className = 'search-with-builder'; input.parentElement.insertBefore(wrapper, input); wrapper.appendChild(input); const button = document.createElement('button'); button.className = 'icon-button'; button.id = 'browseQuickLaunchApp'; button.type = 'button'; button.setAttribute('aria-label', 'Browse for an application to launch invisibly'); button.textContent = '▣'; wrapper.appendChild(button); }
function ensureSubagentPanel() { if ($('subagentPanel')) return; const card = document.createElement('article'); card.className = 'card subagent-panel'; card.id = 'subagentPanel'; card.innerHTML = '<h3>Subagent lanes</h3><p class="support">Persist a named project/agent lane so later agents can pick up the same namespace.</p><div class="inline-form"><label>Project<input id="subagentProject" value="demo-project" /></label><label>Agent<input id="subagentName" value="agent-1" /></label><label>Rooms<input id="subagentCount" type="number" min="1" max="32" value="1" /></label><button class="filled" id="createSubagent" type="button">Create subagent lane</button></div><div id="agentList" class="history-list"></div>'; $('workspace').appendChild(card); $('createSubagent').addEventListener('click', createAgentLane); }
async function ensureReleaseIdentity() { if ($('releaseIdentity')) return; let identity = { codeName: 'Classic Har Gow · 蝦餃', imageUrl: 'https://github.com/Ding-Ding-Projects/dim-sum-photos/releases/download/catalog-v1/hk-dish-0001-classic-har-gow.png', altText: 'Warm tea-house photograph of Classic Har Gow' }; try { identity = { ...identity, ...(await window.lowlevel.getReleaseCodename()) }; } catch { /* the static fallback keeps the About surface usable */ } const host = document.querySelector('[data-appearance="manual"]'); if (!host) return; const card = document.createElement('article'); card.id = 'releaseIdentity'; card.className = 'release-identity'; card.innerHTML = '<h3>Build code name</h3><p><strong>' + escapeHtml(identity.codeName) + '</strong></p><p class="support">Catalog dish names stay factual at every language and funny level. <a href="#" id="releaseDishLink">View the verified catalog photo ↗</a></p>'; host.appendChild(card); $('releaseDishLink').addEventListener('click', async (event) => { event.preventDefault(); if (identity.imageUrl) await window.lowlevel.openExternal(identity.imageUrl); }); }
function ensureTabManagerControls() {
  if ($('tabAdvancedControls')) return;
  const host = document.querySelector('[data-appearance="tab-manager"]');
  if (!host) return;
  const card = document.createElement('section');
  card.id = 'tabAdvancedControls';
  card.className = 'tab-advanced-controls';
  card.innerHTML = '<h4>Groups and bulk close</h4>' +
    '<div class="inline-form tab-group-controls"><label>Group<select id="tabGroupSelect"></select></label><label>Group name<input id="tabGroupName" placeholder="New group name" /></label><button class="tonal" id="addTabGroup" type="button">New group</button><button class="text-button" id="renameTabGroup" type="button">Rename</button><button class="text-button" id="toggleTabGroup" type="button">Collapse / expand</button><button class="text-button" id="moveActiveToGroup" type="button">Move active tab</button></div>' +
    '<div class="bulk-tab-controls"><label>Tab text<input id="tabBulkQuery" placeholder="Required: visible tab label" /></label><label>Scope<select id="tabBulkScope"></select></label><label>Action<select id="tabBulkMode"><option value="containing">Close tabs containing text</option><option value="not-containing">Close tabs not containing text</option></select></label><label class="checkbox-label"><input id="tabBulkIncludePinned" type="checkbox" /> Include pinned tabs</label><button class="icon-button" id="tabBulkRegexToggle" type="button" aria-label="Open bulk tab close regex builder">.*</button><button class="tonal" id="previewTabBulk" type="button">Preview</button><button class="filled" id="applyTabBulk" type="button">Close matching tabs</button></div>' +
    '<div class="regex-panel" id="tabBulkRegexPanel"><label>Pattern<input id="tabBulkRegexPattern" /></label><label>Flags<input id="tabBulkRegexFlags" value="i" /></label><span id="tabBulkRegexResult">Plain text is the default. Regex is opt-in.</span></div>' +
    '<div id="tabBulkPreview" class="bulk-preview" aria-live="polite">Enter text and preview before closing tabs.</div>';
  host.appendChild(card);
  const menu = document.createElement('div');
  menu.id = 'tabContextMenu';
  menu.className = 'tab-context-menu';
  menu.setAttribute('role', 'menu');
  document.body.appendChild(menu);
}
function selectedGroupId() { return $('tabGroupSelect')?.value || Object.keys(tabs.groups)[0]; }
async function createTabGroup() {
  const label = $('tabGroupName').value.trim();
  if (!label) { await notify('Enter a group name before creating it.', '先填 group 名先喇。', 'error'); return; }
  const id = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'group';
  if (tabs.groups[id]) { await notify('That group already exists.', '呢個 group 已經有喇。', 'error'); return; }
  tabs.groups[id] = { label, collapsed: false, tabs: [] };
  $('tabGroupName').value = '';
  await saveTabs();
  $('tabGroupSelect').value = id;
  await notify('Tab group created.', 'Tab group 開好喇。');
}
async function renameTabGroup() {
  const id = selectedGroupId();
  const label = $('tabGroupName').value.trim();
  if (!id || !label) { await notify('Choose a group and enter its new name.', '揀個 group，再填新名。', 'error'); return; }
  tabs.groups[id].label = label;
  $('tabGroupName').value = '';
  await saveTabs();
  await notify('Tab group renamed.', 'Tab group 改好名喇。');
}
async function toggleTabGroup() {
  const id = selectedGroupId();
  if (!id) return;
  tabs.groups[id].collapsed = !tabs.groups[id].collapsed;
  await saveTabs();
  await notify(tabs.groups[id].collapsed ? 'Tab group collapsed.' : 'Tab group expanded.', tabs.groups[id].collapsed ? 'Tab group 收埋喇。' : 'Tab group 展開喇。');
}
async function moveActiveToGroup() {
  const id = selectedGroupId();
  if (!id || !tabs.groups[id]) return;
  removeTabFromGroups(activeTab);
  tabs.groups[id].tabs.push(activeTab);
  await saveTabs();
  await notify('Active tab moved to the selected group.', 'Active tab 搬咗去揀咗嘅 group。');
}
function bulkTabCandidates() {
  const scope = $('tabBulkScope')?.value || 'all';
  if (scope === 'all') return [...tabs.order];
  return tabs.groups[scope] ? tabs.groups[scope].tabs.filter((id) => tabs.order.includes(id)) : [];
}
function bulkTabMatchResult() {
  const query = $('tabBulkQuery')?.value.trim() || '';
  if (!query) return { error: 'Enter text before previewing a bulk close.' };
  const pattern = bulkTabState.pattern.trim();
  let predicate;
  try {
    const safeQuery = query.replace(/[^\w\s-]/g, (char) => '\\' + char);
    const expression = new RegExp(pattern || safeQuery, bulkTabState.flags || 'i');
    predicate = (label) => { expression.lastIndex = 0; return expression.test(label); };
  } catch (error) {
    return { error: 'Invalid bulk-close regex: ' + error.message };
  }
  const includePinned = Boolean($('tabBulkIncludePinned')?.checked);
  const candidates = bulkTabCandidates();
  const eligible = candidates.filter((id) => includePinned || !tabs.pinned.includes(id));
  const containing = eligible.filter((id) => predicate(TAB_LABELS[id]));
  const mode = $('tabBulkMode')?.value || 'containing';
  let affected = mode === 'containing' ? containing : eligible.filter((id) => !containing.includes(id));
  let protectedActive = false;
  if (affected.length === tabs.order.length && affected.includes(activeTab)) {
    affected = affected.filter((id) => id !== activeTab);
    protectedActive = true;
  }
  return { affected, eligible, protectedActive, mode, query, regex: Boolean(pattern) };
}
function previewTabBulk() {
  const result = bulkTabMatchResult();
  const preview = $('tabBulkPreview');
  if (result.error) { preview.textContent = result.error; preview.classList.add('error'); return result; }
  preview.classList.remove('error');
  const labels = result.affected.map((id) => TAB_LABELS[id]);
  const protectedText = result.protectedActive ? ' The active tab is protected so the app keeps a usable page.' : '';
  preview.textContent = result.affected.length ? result.affected.length + ' tab(s) will close: ' + labels.slice(0, 12).join(', ') + (labels.length > 12 ? ', …' : '') + protectedText : 'No tabs match; nothing will close.';
  return result;
}
async function applyTabBulk() {
  const result = previewTabBulk();
  if (result.error || !result.affected?.length) return;
  const labels = result.affected.map((id) => TAB_LABELS[id]).join(', ');
  const action = async () => {
    const removed = new Set(result.affected);
    tabs.order = tabs.order.filter((id) => !removed.has(id));
    tabs.pinned = tabs.pinned.filter((id) => !removed.has(id));
    result.affected.forEach(removeTabFromGroups);
    if (!tabs.order.includes(activeTab)) await navigate(tabs.order[0] || DEFAULT_TABS.order[0]);
    await saveTabs();
    await notify(result.mode === 'containing' ? 'Tabs containing the text were closed.' : 'Tabs not containing the text were closed.', result.mode === 'containing' ? '有呢段字嘅 tabs 關好喇。' : '冇呢段字嘅 tabs 關好喇。');
  };
  openConfirmation(result.mode === 'containing' ? 'Close tabs containing text' : 'Close tabs not containing text', 'This closes: ' + labels + '.', action);
}
function openBulkTabRegex() {
  $('tabBulkRegexPanel').classList.toggle('open');
  $('tabBulkRegexPattern').focus();
}
function updateBulkTabRegex() {
  bulkTabState.pattern = $('tabBulkRegexPattern').value;
  bulkTabState.flags = $('tabBulkRegexFlags').value || 'i';
  try {
    new RegExp(bulkTabState.pattern || '.', bulkTabState.flags);
    $('tabBulkRegexResult').textContent = bulkTabState.pattern ? 'Valid regex active for bulk close.' : 'Plain text is the default. Regex is opt-in.';
  } catch (error) {
    $('tabBulkRegexResult').textContent = 'Invalid regex: ' + error.message;
  }
  previewTabBulk();
}
function renderTabContextMenu() {
  const menu = $('tabContextMenu');
  if (!menu || !contextTab) return;
  const query = menu.querySelector('input')?.value.toLowerCase() || '';
  const groupButtons = Object.entries(tabs.groups).map(([id, group]) => '<button type="button" role="menuitem" data-tab-action="move" data-group-id="' + escapeHtml(id) + '">' + escapeHtml('Move to ' + group.label) + '</button>').join('');
  const items = [
    '<button type="button" role="menuitem" data-tab-action="pin">' + (tabs.pinned.includes(contextTab) ? 'Unpin tab' : 'Pin tab') + '</button>',
    '<button type="button" role="menuitem" data-tab-action="appearance">Edit tab appearance… <kbd>Shift+F10</kbd></button>',
    groupButtons
  ].join('');
  menu.innerHTML = '<label class="menu-search">Search menu<input aria-label="Search tab menu" placeholder="Search tab actions" value="' + escapeHtml(query) + '" /></label><div class="menu-items">' + items + '</div>';
  menu.querySelector('input').addEventListener('input', renderTabContextMenu);
  menu.querySelectorAll('[data-tab-action]').forEach((button) => button.hidden = query && !button.textContent.toLowerCase().includes(query));
  menu.querySelectorAll('[data-tab-action]').forEach((button) => button.addEventListener('click', async () => {
    const action = button.dataset.tabAction;
    if (action === 'pin') tabs.pinned = tabs.pinned.includes(contextTab) ? tabs.pinned.filter((id) => id !== contextTab) : [...tabs.pinned, contextTab];
    if (action === 'move') { removeTabFromGroups(contextTab); tabs.groups[button.dataset.groupId].tabs.push(contextTab); }
    if (action === 'appearance') { const tab = document.querySelector('.tab[data-tab="' + CSS.escape(contextTab) + '"]'); if (tab) openAppearance(tab, contextTab); }
    await saveTabs();
    menu.classList.remove('open');
  }));
}
function openTabContextMenu(event, id) {
  contextTab = id;
  const menu = $('tabContextMenu');
  if (!menu) return;
  renderTabContextMenu();
  const target = document.querySelector('.tab[data-tab="' + CSS.escape(id) + '"]');
  const rect = target?.getBoundingClientRect();
  const x = event.clientX || rect?.left || 12;
  const y = event.clientY || rect?.bottom || 12;
  menu.style.left = Math.min(window.innerWidth - 320, Math.max(8, x)) + 'px';
  menu.style.top = Math.min(window.innerHeight - 260, Math.max(8, y)) + 'px';
  menu.classList.add('open');
  menu.querySelector('input')?.focus();
}
function clamp(value, min = 0, max = 1) { return Math.min(max, Math.max(min, value)); }
function parseHex(value) { const raw = String(value).trim().replace(/^#/, ''); const expanded = raw.length === 3 ? raw.split('').map((part) => part + part).join('') : raw; if (!/^[0-9a-f]{6}$/i.test(expanded)) return null; return { r: parseInt(expanded.slice(0, 2), 16), g: parseInt(expanded.slice(2, 4), 16), b: parseInt(expanded.slice(4, 6), 16) }; }
function rgbToHex(rgb) { return `#${[rgb.r, rgb.g, rgb.b].map((value) => Math.round(clamp(value, 0, 255)).toString(16).padStart(2, '0')).join('')}`; }
function rgbToHsl({ r, g, b }) { r /= 255; g /= 255; b /= 255; const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min; let h = 0; const l = (max + min) / 2; const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1)); if (d) { h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4; h = (h * 60 + 360) % 360; } return { h, s: s * 100, l: l * 100 }; }
function hslToRgb({ h, s, l }) { h = ((h % 360) + 360) % 360 / 360; s = clamp(s / 100); l = clamp(l / 100); const hue = (n) => (n + h * 12) % 12; const a = s * Math.min(l, 1 - l); const f = (n) => l - a * Math.max(-1, Math.min(hue(n) - 3, Math.min(9 - hue(n), 1))); return { r: f(0) * 255, g: f(8) * 255, b: f(4) * 255 }; }
function rgbToHsv({ r, g, b }) { r /= 255; g /= 255; b /= 255; const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min; let h = 0; if (d) h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4; return { h: (h * 60 + 360) % 360, s: max ? d / max * 100 : 0, v: max * 100 }; }
function hsvToRgb({ h, s, v }) { h = ((h % 360) + 360) % 360; s = clamp(s / 100); v = clamp(v / 100); const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c; const values = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x]; return { r: (values[0] + m) * 255, g: (values[1] + m) * 255, b: (values[2] + m) * 255 }; }
function rgbToHwb(rgb) { const hsv = rgbToHsv(rgb); return { h: hsv.h, w: Math.min(rgb.r, rgb.g, rgb.b) / 255 * 100, b: (1 - Math.max(rgb.r, rgb.g, rgb.b) / 255) * 100 }; }
function hwbToRgb({ h, w, b }) { w /= 100; b /= 100; if (w + b >= 1) return { r: w / (w + b) * 255, g: w / (w + b) * 255, b: w / (w + b) * 255 }; const rgb = hsvToRgb({ h, s: 100, v: 100 }); const factor = 1 - w - b; return { r: (rgb.r / 255 * factor + w) * 255, g: (rgb.g / 255 * factor + w) * 255, b: (rgb.b / 255 * factor + w) * 255 }; }
function rgbToCmyk({ r, g, b }) { r /= 255; g /= 255; b /= 255; const k = 1 - Math.max(r, g, b); return { c: k === 1 ? 0 : (1 - r - k) / (1 - k) * 100, m: k === 1 ? 0 : (1 - g - k) / (1 - k) * 100, y: k === 1 ? 0 : (1 - b - k) / (1 - k) * 100, k: k * 100 }; }
function cmykToRgb({ c, m, y, k }) { c /= 100; m /= 100; y /= 100; k /= 100; return { r: 255 * (1 - c) * (1 - k), g: 255 * (1 - m) * (1 - k), b: 255 * (1 - y) * (1 - k) }; }
function parseNumbers(value) { const numbers = String(value).match(/-?\d+(?:\.\d+)?/g); return numbers ? numbers.map(Number) : []; }
function parseColor(space, value) { const numbers = parseNumbers(value); if (space === 'hex') return parseHex(value); if (space === 'rgb' && numbers.length >= 3) return { r: numbers[0], g: numbers[1], b: numbers[2] }; if (space === 'hsl' && numbers.length >= 3) return hslToRgb({ h: numbers[0], s: numbers[1], l: numbers[2] }); if (space === 'hsv' && numbers.length >= 3) return hsvToRgb({ h: numbers[0], s: numbers[1], v: numbers[2] }); if (space === 'hwb' && numbers.length >= 3) return hwbToRgb({ h: numbers[0], w: numbers[1], b: numbers[2] }); if (space === 'cmyk' && numbers.length >= 4) return cmykToRgb({ c: numbers[0], m: numbers[1], y: numbers[2], k: numbers[3] }); return null; }
function colorRepresentations(rgb) { const hsl = rgbToHsl(rgb), hsv = rgbToHsv(rgb), hwb = rgbToHwb(rgb), cmyk = rgbToCmyk(rgb); return { hex: rgbToHex(rgb), rgb: `rgb(${Math.round(rgb.r)} ${Math.round(rgb.g)} ${Math.round(rgb.b)})`, hsl: `hsl(${hsl.h.toFixed(1)} ${hsl.s.toFixed(1)}% ${hsl.l.toFixed(1)}%)`, hsv: `hsv(${hsv.h.toFixed(1)} ${hsv.s.toFixed(1)}% ${hsv.v.toFixed(1)}%)`, hwb: `hwb(${hwb.h.toFixed(1)} ${hwb.w.toFixed(1)}% ${hwb.b.toFixed(1)}%)`, lab: 'Lab values are displayed after conversion support is added.', lch: 'LCH values are displayed after conversion support is added.', oklab: 'OKLab values are displayed after conversion support is added.', oklch: 'OKLCH values are displayed after conversion support is added.', cmyk: `cmyk(${cmyk.c.toFixed(1)}% ${cmyk.m.toFixed(1)}% ${cmyk.y.toFixed(1)}% ${cmyk.k.toFixed(1)}%)`, named: '' }; }
function ensureAppearanceTranslator() { if ($('colorTranslator')) return; const card = document.createElement('article'); card.className = 'card color-translator'; card.id = 'colorTranslator'; card.innerHTML = '<h3>Infinite color picker & translator</h3><p class="support">The continuous color field is the source of truth. HEX, RGB, HSL, HSV, HWB, and CMYK are editable; Lab/LCH and OKLab/OKLCH stay visible with a capability note rather than silently discarding input.</p><label>Color field<input id="translatorColor" type="color" value="#aec6ff" /></label><div class="translator-grid">' + ['hex', 'rgb', 'hsl', 'hsv', 'hwb', 'lab', 'lch', 'oklab', 'oklch', 'cmyk', 'named'].map((space) => `<label>${space.toUpperCase()}<span class="search-with-builder"><input data-color-space="${space}" id="color-${space}" /><button class="icon-button color-copy" data-color-space="${space}" type="button" aria-label="Copy ${space} color">⧉</button></span></label>`).join('') + '</div><p id="colorContrast" class="support"></p>'; const host = document.querySelector('[data-appearance="appearance-editor"]'); if (!host) return; host.appendChild(card); const update = (rgb) => { if (!rgb) return; const reps = colorRepresentations(rgb); $('translatorColor').value = reps.hex; Object.entries(reps).forEach(([space, value]) => { const input = $(`color-${space}`); if (input) input.value = value; }); const luminance = (channel) => { channel /= 255; return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4; }; const contrast = (0.2126 * luminance(rgb.r) + 0.7152 * luminance(rgb.g) + 0.0722 * luminance(rgb.b)); $('colorContrast').textContent = `sRGB gamut: in range · relative luminance ${contrast.toFixed(3)} · contrast is calculated against this app's text color.`; }; $('translatorColor').addEventListener('input', () => { const rgb = parseHex($('translatorColor').value); update(rgb); settings.appearance.accent = rgbToHex(rgb); applySettings(settings); }); card.querySelectorAll('[data-color-space]').forEach((input) => input.addEventListener('change', () => { const rgb = parseColor(input.dataset.colorSpace, input.value); if (rgb) { update(rgb); settings.appearance.accent = rgbToHex(rgb); applySettings(settings); } else if (!['lab', 'lch', 'oklab', 'oklch', 'named'].includes(input.dataset.colorSpace)) input.setCustomValidity('Enter a valid color representation.'); })); card.querySelectorAll('.color-copy').forEach((button) => button.addEventListener('click', async () => { await navigator.clipboard?.writeText($(`color-${button.dataset.colorSpace}`).value); await notify(`${button.dataset.colorSpace.toUpperCase()} color copied.`, `${button.dataset.colorSpace.toUpperCase()} 顏色 copy 好喇。`); })); update(parseHex(settings.appearance.accent)); }

function renderNotifications() { $('notificationCount').textContent = notifications.length; $('notificationList').innerHTML = notifications.length ? notifications.map((entry) => `<article class="history-item"><strong>${escapeHtml(entry.text)}</strong><br><span class="support">${escapeHtml(entry.at)} · ${escapeHtml(entry.level)}</span></article>`).join('') : '<p class="empty">No notifications yet.</p>'; }
async function loadNotifications() { notifications = await window.lowlevel.getNotifications(); renderNotifications(); }

function renderHistoryEntry(entry) { return `<article class="history-item"><code>${escapeHtml(entry.tool)}</code> <span class="support">${escapeHtml(entry.at)}</span><pre>${escapeHtml(JSON.stringify(entry.result, null, 2))}</pre></article>`; }
async function loadHistory() { const query = $('historySearch').value; const matcher = makeMatcher('historySearch', query); const entries = await window.lowlevel.getHistory(); const filtered = entries.filter((entry) => matcher(`${entry.tool} ${JSON.stringify(entry.input)} ${JSON.stringify(entry.result)}`)); $('historyList').innerHTML = filtered.length ? filtered.map(renderHistoryEntry).join('') : '<p class="empty">No matching command history.</p>'; }
function renderChangelog() { const query = $('changelogSearch').value; const matcher = makeMatcher('changelogSearch', query); const from = $('changelogDateFrom').value; const to = $('changelogDateTo').value; const entries = changelogEntries.filter((entry) => (!from || entry.date >= from) && (!to || entry.date <= to) && matcher(`${entry.version} ${entry.title} ${entry.changes.join(' ')}`)); $('changelogList').innerHTML = entries.length ? entries.map((entry) => `<article class="history-item"><h3>${escapeHtml(entry.version)} · ${escapeHtml(entry.title)}</h3><p class="support">${escapeHtml(entry.date)} · <a href="${escapeHtml(entry.url)}" target="_blank" rel="noreferrer">${escapeHtml(entry.commit.slice(0, 12))}</a>${entry.codeName ? ` · Build code name: <a href="${escapeHtml(entry.codeNameUrl || '#')}" target="_blank" rel="noreferrer">${escapeHtml(entry.codeName)}</a>` : ''}</p><ul>${entry.changes.map((change) => `<li>${escapeHtml(change)}</li>`).join('')}</ul></article>`).join('') : '<p class="empty">No changelog entries match the current filters.</p>'; }
async function loadChangelog() { const result = await window.lowlevel.getChangelog(); if (result.ok && result.entries.length) { let identity = {}; try { identity = await window.lowlevel.getReleaseCodename(); } catch { /* static changelog remains useful */ } changelogEntries = result.entries.map((entry, index) => ({ version: entry.commit.slice(0, 12), date: entry.date, title: entry.subject, commit: entry.commit, url: `https://github.com/codingmachineedge/lowlevel-computer-use-mcp/commit/${entry.commit}`, codeName: index === 0 ? identity.codeName : undefined, codeNameUrl: index === 0 ? identity.imageUrl : undefined, changes: entry.body ? entry.body.replace(/\\n/g, '\n').split(/\r?\n/).filter(Boolean).slice(0, 12) : [entry.subject] })); } }

function settingsSearchRefresh() { const matcher = makeMatcher('settingsSearch', $('settingsSearch').value); document.querySelectorAll('[data-setting]').forEach((item) => { item.hidden = !matcher(item.textContent); }); }
function renderTabManager() {
  const searches = { stripSearch: $('stripSearch').value, groupTabSearch: $('groupTabSearch').value, groupSearch: $('groupSearch').value, masterTabSearch: $('masterTabSearch').value };
  const masterMatcher = makeMatcher('masterTabSearch', searches.masterTabSearch);
  const groupMatcher = makeMatcher('groupSearch', searches.groupSearch);
  const groupTabMatcher = makeMatcher('groupTabSearch', searches.groupTabSearch);
  const groupOptions = '<option value="">Ungrouped</option>' + Object.entries(tabs.groups).map(([id, group]) => '<option value="' + escapeHtml(id) + '">' + escapeHtml(group.label) + '</option>').join('');
  const rows = tabs.order.filter((id) => masterMatcher(TAB_LABELS[id])).map((id) => {
    const group = groupForTab(id);
    const groupLabel = group ? group[1].label : 'Ungrouped';
    if (!groupMatcher(groupLabel) || !groupTabMatcher(TAB_LABELS[id])) return '';
    const selectedOptions = groupOptions.replace('value="' + escapeHtml(group?.[0] || '') + '"', 'value="' + escapeHtml(group?.[0] || '') + '" selected');
    return '<article class="history-item"><strong>' + escapeHtml(TAB_LABELS[id]) + '</strong><span class="support">' + escapeHtml(groupLabel) + ' · ' + (tabs.pinned.includes(id) ? 'pinned' : 'ordinary') + '</span><label class="tab-row-group">Group<select data-tab-group="' + escapeHtml(id) + '">' + selectedOptions + '</select></label><button class="text-button tab-pin-action" data-tab-id="' + escapeHtml(id) + '">' + (tabs.pinned.includes(id) ? 'Unpin' : 'Pin') + '</button></article>';
  }).join('');
  const groups = Object.entries(tabs.groups).filter(([, group]) => groupMatcher(group.label)).map(([id, group]) => {
    const members = group.tabs.filter((tabId) => masterMatcher(TAB_LABELS[tabId]) && groupTabMatcher(TAB_LABELS[tabId])).map((tabId) => TAB_LABELS[tabId]).join(', ') || 'No matching tabs';
    return '<article class="tab-group-item"><button class="text-button tab-group-toggle" data-group-id="' + escapeHtml(id) + '" aria-expanded="' + (!group.collapsed) + '">' + escapeHtml(group.label) + ' · ' + group.tabs.length + ' tab(s)</button><p class="support" ' + (group.collapsed ? 'hidden' : '') + '>' + escapeHtml(members) + '</p></article>';
  }).join('');
  $('tabManagerList').innerHTML = (rows || '<p class="empty">No tabs match the active searches.</p>') + '<div class="tab-group-list">' + groups + '</div>';
  renderTabGroupOptions();
  document.querySelectorAll('.tab-pin-action').forEach((button) => button.addEventListener('click', async () => { const id = button.dataset.tabId; tabs.pinned = tabs.pinned.includes(id) ? tabs.pinned.filter((item) => item !== id) : [...tabs.pinned, id]; await saveTabs(); }));
  document.querySelectorAll('[data-tab-group]').forEach((select) => select.addEventListener('change', async () => { const id = select.dataset.tabGroup; removeTabFromGroups(id); if (select.value && tabs.groups[select.value]) tabs.groups[select.value].tabs.push(id); await saveTabs(); }));
  document.querySelectorAll('.tab-group-toggle').forEach((button) => button.addEventListener('click', async () => { const id = button.dataset.groupId; tabs.groups[id].collapsed = !tabs.groups[id].collapsed; await saveTabs(); }));
}

function applySettings(next) { settings = { ...DEFAULT_SETTINGS, ...next, appearance: { ...DEFAULT_SETTINGS.appearance, ...(next.appearance || {}) } }; const root = document.documentElement; root.style.setProperty('--accent', settings.accent); root.style.setProperty('--font-scale', settings.fontScale); root.style.setProperty('--font-family', settings.appearance.font); root.style.setProperty('--font-weight', settings.appearance.weight); root.style.setProperty('--radius', `${settings.appearance.radius}px`); root.style.setProperty('--surface', settings.appearance.surface); root.style.setProperty('--text', settings.appearance.text); root.style.setProperty('--appearance-accent', settings.appearance.accent); root.dataset.density = settings.density; root.dataset.language = settings.language; if (settings.theme === 'light') { root.style.setProperty('--bg', '#f8f8ff'); root.style.setProperty('--surface2', '#e0e3ed'); root.style.setProperty('--muted', '#45464f'); root.style.colorScheme = 'light'; } else { root.style.setProperty('--bg', '#101318'); root.style.setProperty('--surface2', '#232731'); root.style.setProperty('--muted', '#c4c6d0'); root.style.colorScheme = 'dark'; } $('englishFunnyValue').value = settings.englishFunny; $('cantoneseFunnyValue').value = settings.cantoneseFunny; $('englishFunnyValue').textContent = settings.englishFunny; $('cantoneseFunnyValue').textContent = settings.cantoneseFunny; $('appearanceFont').value = settings.appearance.font; $('appearanceWeight').value = settings.appearance.weight; $('appearanceRadius').value = settings.appearance.radius; $('appearanceSurface').value = settings.appearance.surface; $('appearanceText').value = settings.appearance.text; $('appearanceAccent').value = settings.appearance.accent; $('settingsDisclosure').textContent = localized('Funny levels style every app message, including errors and warnings. Facts, command names, paths, and affected data remain exact.', 'Funny level 會幫所有 app 訊息加語氣，包括錯誤同警告；事實、command 名、路徑同受影響資料保持原樣。'); }
async function loadMemory() { memoryEntries = await window.lowlevel.getMemory(); renderMemory(); }
function renderMemory() {
  const list = $('memoryList');
  if (!list) return;
  const matcher = makeMatcher('memorySearch', $('memorySearch')?.value || '');
  const visible = memoryEntries.filter((entry) => matcher(`${entry.label} ${entry.action} ${entry.revision || ''}`));
  list.innerHTML = visible.length ? visible.map((entry) => '<article class="history-item memory-item"><div><strong>' + escapeHtml(entry.label) + '</strong><span class="support">' + escapeHtml(entry.action) + ' · ' + escapeHtml(entry.at) + (entry.revision ? ' · revision ' + escapeHtml(entry.revision.slice(0, 8)) : '') + '</span></div><button class="tonal memory-restore" data-memory-id="' + escapeHtml(entry.id) + '" type="button">Restore</button></article>').join('') : '<p class="empty">No memory checkpoints match this search.</p>';
  document.querySelectorAll('.memory-restore').forEach((button) => button.addEventListener('click', () => {
    const entry = memoryEntries.find((item) => item.id === button.dataset.memoryId);
    if (!entry) return;
    openConfirmation('Restore memory checkpoint', `This replaces settings, connections, agent lanes, and tab layout with “${entry.label}”. A new revision records the restore.`, async () => {
      await window.lowlevel.createMemoryCheckpoint('Before restoring: ' + entry.label);
      const result = await window.lowlevel.restoreMemoryCheckpoint(entry.id);
      if (!result.ok) { await notify(result.error, 'Memory checkpoint 搵唔到喇。', 'error'); return; }
      settings = { ...DEFAULT_SETTINGS, ...result.state.settings, appearance: { ...DEFAULT_SETTINGS.appearance, ...(result.state.settings.appearance || {}) } };
      tabs = normalizeTabs(result.state.tabs); connections = result.state.connections || []; agents = result.state.agents || [];
      applySettings(settings); await window.lowlevel.setSettings(settings); await loadConnections(); renderAgents(); renderTabs(); renderTabManager(); await loadMemory();
      await notify('Memory checkpoint restored and recorded as a new revision.', 'Memory checkpoint 還原好，亦記低咗新 revision。');
    });
  }));
}
async function createMemoryCheckpoint() {
  const label = $('memoryLabel').value.trim();
  if (!label) { await notify('Name the checkpoint before saving it.', '要幫 checkpoint 改個名先喇。', 'error'); return; }
  const entry = await window.lowlevel.createMemoryCheckpoint(label);
  $('memoryLabel').value = '';
  await loadMemory();
  await notify(`Memory checkpoint “${entry.label}” saved.`, `Memory checkpoint「${entry.label}」儲好喇。`);
}
async function exportMemory() {
  const markdown = '# Memory checkpoints\n\n' + memoryEntries.map((entry) => `## ${entry.label}\n\n- Action: ${entry.action}\n- Created: ${entry.at}\n- Revision: ${entry.revision || 'snapshot-only'}\n`).join('\n');
  const file = await window.lowlevel.exportText(markdown);
  await notify(`Memory checkpoints exported to ${file}.`, `Memory checkpoints export 咗去 ${file}。`);
}
async function loadSettings() { applySettings(await window.lowlevel.getSettings()); $('language').value = settings.language; $('englishFunny').value = settings.englishFunny; $('cantoneseFunny').value = settings.cantoneseFunny; $('theme').value = settings.theme; $('density').value = settings.density; $('accent').value = settings.accent; $('fontScale').value = settings.fontScale; }
async function saveSettings() { settings = { ...settings, language: $('language').value, englishFunny: Number($('englishFunny').value), cantoneseFunny: Number($('cantoneseFunny').value), theme: $('theme').value, density: $('density').value, accent: $('accent').value, fontScale: Number($('fontScale').value) }; applySettings(settings); await window.lowlevel.setSettings(settings); await notify('Settings saved for this user.', '使用者設定已經儲存。'); }
async function saveAppearance() { settings.appearance = { font: $('appearanceFont').value || 'Segoe UI', weight: Number($('appearanceWeight').value), radius: Number($('appearanceRadius').value), surface: $('appearanceSurface').value, text: $('appearanceText').value, accent: $('appearanceAccent').value }; applySettings(settings); await window.lowlevel.setSettings(settings); await notify('Appearance applied and persisted.', '外觀已套用並儲存。'); }

function openAppearance(element, target = 'global') { appearanceTarget = target; $('appearanceTarget').textContent = `Editing ${target}`; $('popoverSurface').value = settings.appearance.surface; $('popoverText').value = settings.appearance.text; $('popoverAccent').value = settings.appearance.accent; const rect = element.getBoundingClientRect(); const popover = $('appearancePopover'); popover.style.left = `${Math.min(window.innerWidth - 300, Math.max(12, rect.left))}px`; popover.style.top = `${Math.min(window.innerHeight - 300, rect.bottom + 8)}px`; popover.classList.add('open'); }
async function savePopoverAppearance() { settings.appearance.surface = $('popoverSurface').value; settings.appearance.text = $('popoverText').value; settings.appearance.accent = $('popoverAccent').value; applySettings(settings); await window.lowlevel.setSettings(settings); $('appearancePopover').classList.remove('open'); await notify(`Appearance for ${appearanceTarget} updated.`, `${appearanceTarget} 嘅外觀更新咗。`); }

const paletteItems = () => [
  ...tabs.order.map((id) => ({ label: `Open ${TAB_LABELS[id]}`, detail: 'Destination', run: () => navigate(id) })),
  ...toolCatalogNames.map((name) => ({ label: `Run ${name}`, detail: 'MCP tool', run: () => { navigate('runner'); $('toolName').value = name; $('toolName').focus(); } })),
  { label: 'Language mode', detail: 'Settings', run: () => { navigate('settings'); $('language').focus(); } },
  { label: 'English funny level', detail: 'Settings', run: () => { navigate('settings'); $('englishFunny').focus(); } },
  { label: 'Cantonese funny level', detail: 'Settings', run: () => { navigate('settings'); $('cantoneseFunny').focus(); } },
  { label: 'Theme', detail: 'Settings', run: () => { navigate('settings'); $('theme').focus(); } },
  { label: 'Density', detail: 'Settings', run: () => { navigate('settings'); $('density').focus(); } },
  { label: 'Font scale', detail: 'Settings', run: () => { navigate('settings'); $('fontScale').focus(); } },
  { label: 'Appearance editor', detail: 'Settings', run: () => { navigate('settings'); $('appearanceFont').focus(); } },
  { label: 'Memory checkpoints', detail: 'Memory', run: () => { navigate('memory'); $('memoryLabel').focus(); } },
  { label: 'Run current MCP tool', detail: 'Tool runner', run: () => navigate('runner') },
  { label: 'Install or repair dependencies', detail: 'Quiet setup', run: async () => { navigate('runner'); $('installDeps').click(); } },
  { label: 'Host trusted-LAN API', detail: 'Workspaces', run: () => { navigate('workspace'); $('startApi').focus(); } },
  { label: 'Open full GitHub Pages documentation', detail: 'Documentation', run: () => window.lowlevel.openExternal(DOCS_URL) }
];
function renderPalette() { const query = $('paletteSearch').value; const matcher = makeMatcher('paletteSearch', query); const items = paletteItems().filter((item) => matcher(`${item.label} ${item.detail}`)); $('paletteResults').innerHTML = items.length ? items.map((item, index) => `<button class="palette-item" data-palette-index="${index}"><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.detail)}</span></button>`).join('') : '<p class="empty">No commands or destinations match.</p>'; document.querySelectorAll('.palette-item').forEach((button) => button.addEventListener('click', async () => { const item = items[Number(button.dataset.paletteIndex)]; $('commandPalette').close(); await item.run(); })); }

function bindEvents() {
  $('browseProjectFolder').addEventListener('click', async () => { const selected = await window.lowlevel.browsePath('folder'); if (selected) $('project').value = selected; });
  $('browseQuickLaunchApp').addEventListener('click', async () => { const selected = await window.lowlevel.browsePath('app'); if (selected) $('launchCommand').value = selected; });
  $('browseLaunchApp').addEventListener('click', async () => { const selected = await window.lowlevel.browsePath('app'); if (selected) $('launchCommand').value = selected; });
  $('browseToolFile').addEventListener('click', async () => { const selected = await window.lowlevel.browsePath('file'); if (selected) setToolPath(selected); });
  $('browseToolFolder').addEventListener('click', async () => { const selected = await window.lowlevel.browsePath('folder'); if (selected) setToolPath(selected); });
  $('createDesktops').addEventListener('click', async () => { const prefix = `${$('project').value}-${$('agent').value}`.replace(/[^A-Za-z0-9_-]/g, '-'); const result = await run('create_headless_desktops', { count: Number($('desktopCount').value), prefix }); if (result.ok) { await refreshDesktops(); await notify('Headless desktops are ready without touching the visible desktop.', 'Headless desktop 開好喇，冇掂到你個畫面。'); } });
  $('refreshDesktops').addEventListener('click', refreshDesktops);
  $('launchApp').addEventListener('click', async () => { const result = await run('launch_on_headless_desktop', { name: $('desktopSelect').value, command: $('launchCommand').value }); if (result.ok) await notify('Application launched on the selected hidden desktop.', '程式已經喺揀咗嘅隱形 desktop 開好。'); });
  $('startApi').addEventListener('click', async () => { const result = await window.lowlevel.startApi($('apiHost').value, Number($('apiPort').value)); $('apiResult').textContent = result.ok ? `Running at http://${result.host}:${result.port}/mcp · health ${result.health}` : result.error; await notify(result.ok ? 'Trusted-LAN API is hosted headless.' : 'API did not start.', result.ok ? '可信 LAN API 已經用 headless 方式開好。' : 'API 開唔到。', result.ok ? 'info' : 'error'); });
  $('stopApi').addEventListener('click', async () => { await window.lowlevel.stopApi(); $('apiResult').textContent = 'Stopped'; await notify('Trusted-LAN API stopped.', '可信 LAN API 停咗。'); });
  $('installStartup').addEventListener('click', async () => { const result = await window.lowlevel.installStartup($('apiHost').value, Number($('apiPort').value), false); $('apiResult').textContent = result.ok ? 'API scheduled at user logon.' : (result.stderr || result.stdout || 'Startup installation failed.'); await notify(result.ok ? 'Run on logon enabled.' : 'Startup installation needs attention.', result.ok ? '登入時自動開機制已啟用。' : '自動開機制要睇睇。', result.ok ? 'info' : 'error'); });
  $('removeStartup').addEventListener('click', async () => { const result = await window.lowlevel.removeStartup(); $('apiResult').textContent = result.ok ? 'Logon task removed.' : (result.stderr || result.stdout || 'Could not remove startup task.'); await notify(result.ok ? 'Run on logon removed.' : 'Startup removal needs attention.', result.ok ? '登入自動開機制已移除。' : '移除自動開機制要睇睇。', result.ok ? 'info' : 'error'); });
  $('connectRemote').addEventListener('click', async () => { const name = $('remoteName').value.trim(); const url = $('remoteUrl').value.trim().replace(/\/$/, ''); if (!name || !url) { await notify('Name and API URL are required.', '要填名稱同 API URL。', 'error'); return; } const result = await window.lowlevel.remoteCall(url, 'list_headless_desktops', {}); if (!result.ok) { $('remoteStatus').textContent = result.error || 'Remote connection failed.'; await notify('Could not connect to the remote API.', '連唔到另一部電腦嘅 API。', 'error'); return; } const existing = connections.find((item) => item.url === url); const item = existing || { id: `${Date.now()}`, name, url }; item.name = name; connections = [...connections.filter((candidate) => candidate.id !== item.id), item]; await window.lowlevel.setConnections(connections); await loadConnections(); $('remoteSelect').value = item.id; $('targetConnection').value = item.id; $('remoteStatus').textContent = `Connected: ${url}/api/execute · headless desktop preferred`; await notify('Remote computer saved for later agents.', '另一部電腦已儲低，之後 agent 可以拎返嚟用。'); });
  $('remoteSelect').addEventListener('change', () => { $('targetConnection').value = $('remoteSelect').value; });
  $('runTool').addEventListener('click', async () => { try { await run($('toolName').value, json('toolInput')); } catch (error) { await notify(error.message, '參數 JSON 有問題。', 'error'); } });
  $('installDeps').addEventListener('click', async () => { setStatus(localized('Installing quietly…', '靜靜安裝緊…')); const result = await window.lowlevel.bootstrap(); setStatus(result.ok ? localized('Ready', '準備好喇') : localized('Needs attention', '要睇睇喇')); await notify(result.ok ? 'Dependencies and AutoHotkey are ready.' : `Dependency setup stopped at ${result.stage}.`, result.ok ? '依賴同 AutoHotkey 準備好喇。' : `依賴安裝喺 ${result.stage} 停咗。`, result.ok ? 'info' : 'error'); });
  $('historySearch').addEventListener('input', loadHistory); $('regexPattern').addEventListener('input', loadHistory); $('regexFlags').addEventListener('input', loadHistory); wireRegexToggle('regexToggle', 'regexPanel'); wireRegexInputs('historySearch', 'regexPattern', 'regexFlags', 'regexResult', loadHistory);
  $('exportHistory').addEventListener('click', async () => { const entries = await window.lowlevel.getHistory(); const file = await window.lowlevel.exportText(`# Low-Level Computer-Use history\n\n${entries.map((entry) => `## ${entry.tool} — ${entry.at}\n\n\`\`\`json\n${JSON.stringify(entry.result, null, 2)}\n\`\`\``).join('\n\n')}`); await notify(`History exported to ${file}.`, `History export 咗去 ${file}。`); });
  $('clearNotifications').addEventListener('click', () => openConfirmation('Clear notification history', 'This permanently removes the local notification history.', async () => { await window.lowlevel.clearNotifications(); notifications = []; renderNotifications(); await notify('Notification history cleared.', '通知 history 清理好喇。'); }));
  $('notificationOpen').addEventListener('click', () => navigate('notifications')); $('commandPaletteOpen').addEventListener('click', openPalette);
  $('openDocs').addEventListener('click', () => window.lowlevel.openExternal(DOCS_URL));
  $('saveSettings').addEventListener('click', saveSettings); $('englishFunny').addEventListener('input', () => { $('englishFunnyValue').textContent = $('englishFunny').value; }); $('cantoneseFunny').addEventListener('input', () => { $('cantoneseFunnyValue').textContent = $('cantoneseFunny').value; });
  $('saveAppearance').addEventListener('click', saveAppearance); $('resetAppearance').addEventListener('click', async () => { settings.appearance = { ...DEFAULT_SETTINGS.appearance }; applySettings(settings); await window.lowlevel.setSettings(settings); await notify('Appearance reset to the default.', '外觀已重設做預設值。'); }); $('exportSettings').addEventListener('click', async () => { const file = await window.lowlevel.exportText(JSON.stringify({ settings, tabs, connections }, null, 2)); await notify(`Settings exported to ${file}.`, `設定 export 咗去 ${file}。`); }); $('importSettings').addEventListener('click', () => $('settingsFile').click()); $('settingsFile').addEventListener('change', async () => { const file = $('settingsFile').files[0]; if (!file) return; try { const imported = JSON.parse(await file.text()); if (imported.settings) { applySettings(imported.settings); await window.lowlevel.setSettings(settings); } if (imported.tabs) { tabs = normalizeTabs(imported.tabs); await saveTabs(); } if (imported.connections) { connections = imported.connections; await window.lowlevel.setConnections(connections); await loadConnections(); } await notify('Settings imported.', '設定 import 好喇。'); } catch (error) { await notify(`Import failed: ${error.message}`, `Import 失敗：${error.message}`, 'error'); } });
  $('settingsSearch').addEventListener('input', settingsSearchRefresh); wireRegexToggle('settingsRegexToggle', 'settingsRegexPanel'); wireRegexInputs('settingsSearch', 'settingsRegexPattern', 'settingsRegexFlags', 'settingsRegexResult', settingsSearchRefresh);
  ['stripSearch', 'groupTabSearch', 'groupSearch', 'masterTabSearch'].forEach((id) => { regexStates[id] = { pattern: '', flags: 'i' }; $(id).addEventListener('input', () => { renderTabs(); renderTabManager(); }); }); document.querySelectorAll('.tab-regex').forEach((button) => button.addEventListener('click', () => openTabRegex(button.dataset.target))); $('tabRegexPattern').addEventListener('input', updateTabRegex); $('tabRegexFlags').addEventListener('input', updateTabRegex);
  $('addTabGroup').addEventListener('click', createTabGroup); $('renameTabGroup').addEventListener('click', renameTabGroup); $('toggleTabGroup').addEventListener('click', toggleTabGroup); $('moveActiveToGroup').addEventListener('click', moveActiveToGroup);
  $('tabBulkQuery').addEventListener('input', previewTabBulk); $('tabBulkScope').addEventListener('change', () => { $('tabBulkScope').dataset.selected = $('tabBulkScope').value; previewTabBulk(); }); $('tabBulkMode').addEventListener('change', previewTabBulk); $('tabBulkIncludePinned').addEventListener('change', previewTabBulk); $('tabBulkRegexToggle').addEventListener('click', openBulkTabRegex); $('tabBulkRegexPattern').addEventListener('input', updateBulkTabRegex); $('tabBulkRegexFlags').addEventListener('input', updateBulkTabRegex); $('previewTabBulk').addEventListener('click', previewTabBulk); $('applyTabBulk').addEventListener('click', applyTabBulk);
  $('pinActiveTab').addEventListener('click', async () => { tabs.pinned = tabs.pinned.includes(activeTab) ? tabs.pinned.filter((id) => id !== activeTab) : [...tabs.pinned, activeTab]; await saveTabs(); }); $('moveActiveTab').addEventListener('click', async () => { const index = tabs.order.indexOf(activeTab); tabs.order.splice(index, 1); tabs.order.splice((index + 1) % (tabs.order.length + 1), 0, activeTab); await saveTabs(); }); $('resetTabs').addEventListener('click', () => openConfirmation('Reset tab layout', 'This replaces your saved order, pins, and groups with the default layout.', async () => { tabs = JSON.parse(JSON.stringify(DEFAULT_TABS)); await saveTabs(); }));
  $('changelogSearch').addEventListener('input', renderChangelog); $('changelogDateFrom').addEventListener('input', renderChangelog); $('changelogDateTo').addEventListener('input', renderChangelog); $('changelogRegexPattern').addEventListener('input', renderChangelog); $('changelogRegexFlags').addEventListener('input', renderChangelog); wireRegexToggle('changelogRegexToggle', 'changelogRegexPanel'); wireRegexInputs('changelogSearch', 'changelogRegexPattern', 'changelogRegexFlags', 'changelogRegexResult', renderChangelog); $('exportChangelog').addEventListener('click', async () => { const file = await window.lowlevel.exportText(changelogEntries.map((entry) => `# ${entry.version} — ${entry.title}\n\nReleased ${entry.date}; commit ${entry.commit}\n\n${entry.changes.map((change) => `- ${change}`).join('\n')}`).join('\n\n')); await notify(`Changelog exported to ${file}.`, `Changelog export 咗去 ${file}。`); });
  $('memorySearch').addEventListener('input', renderMemory); $('memoryRegexPattern').addEventListener('input', renderMemory); $('memoryRegexFlags').addEventListener('input', renderMemory); wireRegexToggle('memoryRegexToggle', 'memoryRegexPanel'); wireRegexInputs('memorySearch', 'memoryRegexPattern', 'memoryRegexFlags', 'memoryRegexResult', renderMemory); $('createMemoryCheckpoint').addEventListener('click', createMemoryCheckpoint); $('exportMemory').addEventListener('click', exportMemory);
  $('paletteSearch').addEventListener('input', renderPalette); $('paletteRegexToggle').addEventListener('click', () => $('paletteRegexPanel').classList.toggle('open')); wireRegexInputs('paletteSearch', 'paletteRegexPattern', 'paletteRegexFlags', 'paletteRegexResult', renderPalette);
  $('savePopoverAppearance').addEventListener('click', savePopoverAppearance); $('closeAppearancePopover').addEventListener('click', () => $('appearancePopover').classList.remove('open')); document.addEventListener('contextmenu', (event) => { const target = event.target.closest('[data-appearance]'); if (target) { event.preventDefault(); openAppearance(target, target.dataset.appearance); } }); document.addEventListener('click', (event) => { const menu = $('tabContextMenu'); if (menu?.classList.contains('open') && !menu.contains(event.target) && !event.target.closest('.tab')) menu.classList.remove('open'); }); document.addEventListener('keydown', (event) => { if (event.key === 'Escape') $('tabContextMenu')?.classList.remove('open'); if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); } if (event.key === 'F10' && event.shiftKey && document.activeElement?.matches('[data-appearance]')) { event.preventDefault(); openAppearance(document.activeElement, document.activeElement.dataset.appearance); } });
  $('confirmCancel').addEventListener('click', () => $('confirmDialog').close()); $('confirmKeyOne').addEventListener('click', () => { $('confirmKeyOne').classList.toggle('armed'); updateConfirmation(); }); $('confirmKeyTwo').addEventListener('click', () => { $('confirmKeyTwo').classList.toggle('armed'); updateConfirmation(); }); $('confirmSlider').addEventListener('input', updateConfirmation); $('confirmCommit').addEventListener('click', async () => { const action = $('confirmDialog')._action; $('confirmDialog').close(); $('confirmKeyOne').classList.remove('armed'); $('confirmKeyTwo').classList.remove('armed'); $('confirmSlider').value = 0; $('confirmCommit').disabled = true; await action?.(); });
}
function updateConfirmation() { const ready = $('confirmKeyOne').classList.contains('armed') && $('confirmKeyTwo').classList.contains('armed'); $('confirmSlider').disabled = !ready; $('confirmCommit').disabled = !ready || Number($('confirmSlider').value) < 100; }
function openConfirmation(title, body, action) { $('confirmTitle').textContent = title; $('confirmBody').textContent = body; $('confirmDialog')._action = action; $('confirmDialog').showModal(); }
function openPalette() { $('commandPalette').showModal(); $('paletteSearch').value = ''; renderPalette(); $('paletteSearch').focus(); }
window.__captureTab = async (id) => {
  await navigate(id === 'settings-tabs' ? 'settings' : id);
  if (id === 'settings-tabs') $('tabAdvancedControls')?.scrollIntoView({ block: 'start', inline: 'nearest' });
  $('statusText').textContent = 'Screenshot preview';
  return true;
};

function setToolPath(selected) { try { const input = json('toolInput'); input.path = selected; $('toolInput').value = JSON.stringify(input, null, 2); } catch { $('toolInput').value = JSON.stringify({ path: selected }, null, 2); } }
async function bootstrap() { ensurePathBrowser(); ensureQuickLaunchBrowser(); ensureSubagentPanel(); ensureTabManagerControls(); ensureAppearanceTranslator(); await ensureReleaseIdentity(); bindEvents(); tabs = normalizeTabs(await window.lowlevel.getTabs()); await loadSettings(); await loadConnections(); await loadAgents(); await loadTools(); await loadNotifications(); await loadChangelog(); await loadMemory(); renderTabs(); renderTabManager(); renderChangelog(); await refreshDesktops(); }
bootstrap().catch((error) => { setStatus('Needs attention'); show(error.message); });
