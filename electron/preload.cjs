const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lowlevel', {
  runTool: (name, input) => ipcRenderer.invoke('tool:run', name, input),
  bootstrap: () => ipcRenderer.invoke('bootstrap'),
  remoteCall: (baseUrl, tool, input) => ipcRenderer.invoke('remote:call', baseUrl, tool, input),
  getConnections: () => ipcRenderer.invoke('connections:get'),
  setConnections: (connections) => ipcRenderer.invoke('connections:set', connections),
  startApi: (host, port) => ipcRenderer.invoke('api:start', host, port),
  stopApi: () => ipcRenderer.invoke('api:stop'),
  apiStatus: () => ipcRenderer.invoke('api:status'),
  installStartup: (host, port, admin) => ipcRenderer.invoke('startup:install', host, port, admin),
  removeStartup: () => ipcRenderer.invoke('startup:remove'),
  startupStatus: () => ipcRenderer.invoke('startup:status'),
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (settings) => ipcRenderer.invoke('settings:set', settings),
  getHistory: () => ipcRenderer.invoke('history:get'),
  exportText: (text) => ipcRenderer.invoke('export:text', text),
  openExternal: (url) => ipcRenderer.invoke('open:external', url)
});
