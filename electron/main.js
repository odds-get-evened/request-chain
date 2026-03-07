const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

// ── Configuration ─────────────────────────────────────────────────────────────
const FLASK_PORT = 5000;
const FLASK_BASE = `http://127.0.0.1:${FLASK_PORT}`;
const P2P_PORT = parseInt(process.argv[2]) || 6000;
const BACKEND_SCRIPT = path.join(__dirname, '..', 'electron_backend.py');
const POLL_INTERVAL_MS = 300;
const POLL_MAX_ATTEMPTS = 50;  // 15 seconds total

let mainWindow = null;
let pythonProcess = null;
let isDev = process.argv.includes('--dev');

// ── Spawn Python backend ──────────────────────────────────────────────────────
function spawnBackend() {
  const pythonExe = process.platform === 'win32' ? 'python' : 'python3';
  console.log(`Spawning backend: ${pythonExe} ${BACKEND_SCRIPT} ${P2P_PORT}`);
  pythonProcess = spawn(pythonExe, [BACKEND_SCRIPT, String(P2P_PORT)], {
    cwd: path.join(__dirname, '..'),
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', (data) => {
    process.stdout.write(`[backend] ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    process.stderr.write(`[backend] ${data}`);
  });

  pythonProcess.on('exit', (code) => {
    console.log(`Backend exited with code ${code}`);
    if (mainWindow && !app.isQuitting) {
      mainWindow.webContents.send('backend-died', code);
    }
  });
}

// ── Poll Flask until ready ────────────────────────────────────────────────────
function waitForFlask(attempts = 0) {
  return new Promise((resolve, reject) => {
    function tryPing() {
      http.get(`${FLASK_BASE}/api/ping`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      }).on('error', () => {
        retry();
      });
    }

    function retry() {
      if (attempts >= POLL_MAX_ATTEMPTS) {
        reject(new Error('Backend did not start in time'));
        return;
      }
      attempts++;
      setTimeout(tryPing, POLL_INTERVAL_MS);
    }

    tryPing();
  });
}

// ── Create main window ────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#0f1117',
    title: `Request Chain — Port ${P2P_PORT}`,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadURL(`${FLASK_BASE}/`);

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── Menu ──────────────────────────────────────────────────────────────────────
function buildMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Save Chain',
          accelerator: 'CmdOrCtrl+Shift+S',
          click: () => mainWindow?.webContents.send('menu-action', 'save-chain'),
        },
        {
          label: 'Load Chain',
          click: () => mainWindow?.webContents.send('menu-action', 'load-chain'),
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: 'CmdOrCtrl+Q',
          click: () => { app.isQuitting = true; app.quit(); },
        },
      ],
    },
    {
      label: 'Network',
      submenu: [
        {
          label: 'Connect to Peer…',
          accelerator: 'CmdOrCtrl+N',
          click: () => mainWindow?.webContents.send('menu-action', 'connect-peer'),
        },
        {
          label: 'Sync Chain',
          accelerator: 'CmdOrCtrl+S',
          click: () => mainWindow?.webContents.send('menu-action', 'sync-chain'),
        },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        ...(isDev ? [{ type: 'separator' }, { role: 'toggleDevTools' }] : []),
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
ipcMain.handle('get-flask-port', () => FLASK_PORT);
ipcMain.handle('get-p2p-port', () => P2P_PORT);

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.on('ready', async () => {
  spawnBackend();
  buildMenu();

  try {
    await waitForFlask();
    console.log('Backend ready, opening window');
    createWindow();
  } catch (err) {
    console.error('Failed to start backend:', err.message);
    dialog.showErrorBox('Startup Error', `Could not start the backend process.\n\n${err.message}`);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.isQuitting = true;
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  if (pythonProcess) {
    pythonProcess.kill('SIGTERM');
    // Force kill after 3s if still running
    setTimeout(() => {
      if (pythonProcess) pythonProcess.kill('SIGKILL');
    }, 3000);
  }
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});
