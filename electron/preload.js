const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Menu actions forwarded from main process
  onMenuAction: (cb) => ipcRenderer.on('menu-action', (_event, action) => cb(action)),
  // Backend died notification
  onBackendDied: (cb) => ipcRenderer.on('backend-died', (_event, code) => cb(code)),
  // Port queries
  getFlaskPort: () => ipcRenderer.invoke('get-flask-port'),
  getP2PPort: () => ipcRenderer.invoke('get-p2p-port'),
});
