'use strict';

const {
  app, BrowserWindow, ipcMain, Tray, Menu,
  nativeImage, shell, dialog,
} = require('electron');
const { spawn, exec } = require('child_process');
const path  = require('path');
const os    = require('os');
const fs    = require('fs');

// ── Paths ──────────────────────────────────────────────────────────────────

const IS_WIN  = os.platform() === 'win32';
const IS_MAC  = os.platform() === 'darwin';
const IS_PROD = app.isPackaged;

// When packaged, extraResources lands next to the app in resources/
const ROOT_DIR     = IS_PROD
  ? path.join(process.resourcesPath, '..')   // one level above resources/
  : path.join(__dirname, '..');              // project root in dev

const BACKEND_DIR  = IS_PROD
  ? path.join(process.resourcesPath, 'backend')
  : path.join(ROOT_DIR, 'backend');

const FRONTEND_DIR = IS_PROD
  ? path.join(process.resourcesPath, 'frontend-dist')
  : path.join(ROOT_DIR, 'frontend');

const VENV_PYTHON  = IS_WIN
  ? path.join(ROOT_DIR, 'venv', 'Scripts', 'python.exe')
  : path.join(ROOT_DIR, 'venv', 'bin', 'python');

const NPM_CMD      = IS_WIN ? 'npm.cmd' : 'npm';

const BACKEND_PORT  = 8000;
const FRONTEND_PORT = 3000;

// ── State ──────────────────────────────────────────────────────────────────

let loadingWin  = null;
let mainWin     = null;
let tray        = null;
let backendProc = null;
let frontendProc = null;
let isQuitting  = false;

// ── Logging ────────────────────────────────────────────────────────────────

const LOG_FILE = path.join(app.getPath('userData'), 'mnair-desktop.log');
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  process.stdout.write(line);
  try { fs.appendFileSync(LOG_FILE, line); } catch (_) {}
}

// ── IPC helpers ───────────────────────────────────────────────────────────

function sendStatus(step, state, message) {
  log(`[${step}] ${state}: ${message}`);
  if (loadingWin && !loadingWin.isDestroyed()) {
    loadingWin.webContents.send('status', { step, state, message });
  }
}

function sendError(msg) {
  log(`ERROR: ${msg}`);
  if (loadingWin && !loadingWin.isDestroyed()) {
    loadingWin.webContents.send('error', msg);
  }
}

// ── Windows ────────────────────────────────────────────────────────────────

function createLoadingWindow() {
  loadingWin = new BrowserWindow({
    width: 440,
    height: 360,
    frame: false,
    resizable: false,
    center: true,
    alwaysOnTop: true,
    backgroundColor: '#0A0E1A',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  loadingWin.loadFile(path.join(__dirname, 'loading.html'));
}

function createMainWindow() {
  mainWin = new BrowserWindow({
    width: 1300,
    height: 840,
    minWidth: 960,
    minHeight: 600,
    title: 'MNAIR — Make Nigeria AI Ready',
    backgroundColor: '#0A0E1A',
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const url = IS_PROD
    ? `http://localhost:${FRONTEND_PORT}`
    : `http://localhost:${FRONTEND_PORT}`;

  mainWin.loadURL(url);

  mainWin.once('ready-to-show', () => {
    if (loadingWin && !loadingWin.isDestroyed()) {
      loadingWin.close();
      loadingWin = null;
    }
    mainWin.show();
    mainWin.focus();
  });

  // Minimize to tray instead of closing
  mainWin.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWin.hide();
      if (IS_WIN && tray) {
        tray.displayBalloon({
          title: 'MNAIR',
          content: 'Running in the background. Right-click the tray icon to quit.',
        });
      }
    }
  });

  // Open external links in the default browser
  mainWin.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ── Tray ───────────────────────────────────────────────────────────────────

function createTray() {
  let icon;
  const iconPath = path.join(__dirname, 'assets', 'icon.png');
  if (fs.existsSync(iconPath)) {
    icon = nativeImage.createFromPath(iconPath);
  } else {
    // Inline 16x16 green (#008751) PNG as fallback
    const buf = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAMElEQVQ4T2NkYGD4' +
      'z8BAAoxSgFEKRi2gFox6YNQCKvDAqAVGLTBqAVQLAAD//wMABf4D/v2qnkUAAAAA' +
      'SUVORK5CYII=',
      'base64'
    );
    icon = nativeImage.createFromBuffer(buf);
  }

  tray = new Tray(icon);
  tray.setToolTip('MNAIR — Make Nigeria AI Ready');

  const menu = Menu.buildFromTemplate([
    {
      label: 'Open MNAIR',
      click: () => { mainWin?.show(); mainWin?.focus(); },
    },
    { type: 'separator' },
    {
      label: 'Open in Browser',
      click: () => shell.openExternal(`http://localhost:${FRONTEND_PORT}`),
    },
    {
      label: 'API Docs',
      click: () => shell.openExternal(`http://localhost:${BACKEND_PORT}/docs`),
    },
    {
      label: 'View Logs',
      click: () => shell.openPath(LOG_FILE),
    },
    { type: 'separator' },
    {
      label: 'Quit MNAIR',
      click: () => { isQuitting = true; app.quit(); },
    },
  ]);

  tray.setContextMenu(menu);
  tray.on('double-click', () => { mainWin?.show(); mainWin?.focus(); });
}

// ── Port polling (TCP socket — works on both IPv4 and IPv6) ──────────────

const net = require('net');

function waitForPort(port, timeoutMs = 90000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const attempt = () => {
      const sock = new net.Socket();
      const fail = () => {
        sock.destroy();
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`Port ${port} not ready after ${timeoutMs / 1000}s`));
        } else {
          setTimeout(attempt, 1500);
        }
      };
      sock.setTimeout(2000);
      sock.on('connect', () => { sock.destroy(); resolve(); });
      sock.on('error',   fail);
      sock.on('timeout', fail);
      // Try localhost (resolves to ::1 or 127.0.0.1 as needed)
      sock.connect(port, 'localhost');
    };
    attempt();
  });
}

// ── Service launchers ──────────────────────────────────────────────────────

function startDocker() {
  return new Promise((resolve) => {
    sendStatus('docker', 'loading', 'Starting infrastructure…');

    // Check if docker is available first
    exec('docker info', (err) => {
      if (err) {
        sendStatus('docker', 'done', 'Docker not found — using existing services');
        return resolve();
      }

      const proc = exec('docker compose up -d', { cwd: ROOT_DIR });
      proc.on('close', () => {
        sendStatus('docker', 'done', 'Infrastructure ready');
        resolve();
      });
      proc.on('error', () => {
        // Services may already be running — continue
        sendStatus('docker', 'done', 'Infrastructure ready');
        resolve();
      });
    });
  });
}

// Kill whatever process is holding a port (best-effort, always resolves)
function killPortProcess(port) {
  return new Promise((resolve) => {
    if (IS_WIN) {
      // netstat gives us PID; taskkill kills it
      exec(
        `for /f "tokens=5" %a in ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') do taskkill /F /PID %a`,
        { shell: 'cmd.exe' },
        () => resolve()
      );
    } else {
      exec(`lsof -ti:${port} | xargs kill -9 2>/dev/null; true`, () => resolve());
    }
  });
}

function startBackend() {
  return new Promise((resolve, reject) => {
    sendStatus('backend', 'loading', 'Starting API server…');

    // 4 s check — long enough to catch a backend that is mid-startup
    waitForPort(BACKEND_PORT, 4000)
      .then(() => {
        log('Backend already running on port ' + BACKEND_PORT);
        sendStatus('backend', 'done', 'API server ready');
        resolve();
      })
      .catch(async () => {
        if (!fs.existsSync(VENV_PYTHON)) {
          const msg = `Python venv not found at: ${VENV_PYTHON}\nRun the setup steps from SETUP.md first.`;
          sendStatus('backend', 'error', 'Python venv not found');
          return reject(new Error(msg));
        }

        // Kill any stale process that might be occupying the port
        log('Clearing any stale process on port ' + BACKEND_PORT);
        await killPortProcess(BACKEND_PORT);
        // Brief pause so the OS releases the socket before we bind again
        await new Promise(r => setTimeout(r, 600));

        backendProc = spawn(
          VENV_PYTHON,
          ['-m', 'uvicorn', 'app.main:app',
           '--host', '0.0.0.0',
           '--port', String(BACKEND_PORT),
           '--log-level', 'warning'],
          {
            cwd: BACKEND_DIR,
            env: { ...process.env },
            windowsHide: true,
          }
        );

        backendProc.stdout?.on('data', (d) => log('[backend] ' + d.toString().trim()));
        backendProc.stderr?.on('data', (d) => log('[backend] ' + d.toString().trim()));
        backendProc.on('error', (err) => {
          sendStatus('backend', 'error', err.message);
          reject(err);
        });

        waitForPort(BACKEND_PORT, 90000)
          .then(() => {
            sendStatus('backend', 'done', 'API server ready');
            resolve();
          })
          .catch((err) => {
            sendStatus('backend', 'error', 'Timed out waiting for API server');
            reject(err);
          });
      });
  });
}

function startFrontend() {
  return new Promise((resolve, reject) => {
    sendStatus('frontend', 'loading', 'Starting dashboard…');

    // Already running?
    waitForPort(FRONTEND_PORT, 2000)
      .then(() => {
        log('Frontend already running on port ' + FRONTEND_PORT);
        sendStatus('frontend', 'done', 'Dashboard ready');
        resolve();
      })
      .catch(() => {
        if (IS_PROD) {
          // In production build: serve the pre-built dist with a simple static server
          startStaticFrontend().then(resolve).catch(reject);
        } else {
          // In dev: launch Vite dev server
          frontendProc = spawn(NPM_CMD, ['run', 'dev'], {
            cwd: FRONTEND_DIR,
            env: { ...process.env },
            shell: IS_WIN,
            windowsHide: true,
          });

          frontendProc.stdout?.on('data', (d) => log('[frontend] ' + d.toString().trim()));
          frontendProc.stderr?.on('data', (d) => log('[frontend] ' + d.toString().trim()));
          frontendProc.on('error', (err) => {
            sendStatus('frontend', 'error', err.message);
            reject(err);
          });

          waitForPort(FRONTEND_PORT, 60000)
            .then(() => {
              sendStatus('frontend', 'done', 'Dashboard ready');
              resolve();
            })
            .catch((err) => {
              sendStatus('frontend', 'error', 'Timed out waiting for dashboard');
              reject(err);
            });
        }
      });
  });
}

function startStaticFrontend() {
  // Serve the pre-built frontend using Node's built-in http module
  return new Promise((resolve, reject) => {
    const serveStatic = require('electron-serve');
    // electron-serve handles SPA routing properly
    const serve = serveStatic({ directory: FRONTEND_DIR });
    // We need a window to serve into — we'll use it during createMainWindow
    // Store serve fn for later use
    app._serveStatic = serve;
    resolve();
  });
}

// ── App lifecycle ──────────────────────────────────────────────────────────

async function boot() {
  log('=== MNAIR Desktop starting ===');
  log(`Platform: ${os.platform()}, packaged: ${IS_PROD}`);
  log(`Root: ${ROOT_DIR}`);

  createLoadingWindow();

  // Give the loading window a moment to render
  await new Promise(r => setTimeout(r, 400));

  try {
    await startDocker();
    await startBackend();
    await startFrontend();

    sendStatus('launch', 'loading', 'Opening MNAIR…');
    await new Promise(r => setTimeout(r, 600));
    sendStatus('launch', 'done', 'Ready');
    await new Promise(r => setTimeout(r, 300));

    createMainWindow();
    createTray();

  } catch (err) {
    log('FATAL: ' + err.message);
    sendError('Startup failed: ' + err.message);

    // Show an error dialog after a short delay so the user can read the loading screen
    await new Promise(r => setTimeout(r, 2000));
    dialog.showErrorBox('MNAIR failed to start', err.message + '\n\nCheck the log at:\n' + LOG_FILE);
    app.quit();
  }
}

app.whenReady().then(boot);

app.on('activate', () => {
  // macOS: re-show when clicking the dock icon
  if (mainWin) {
    mainWin.show();
  } else {
    boot();
  }
});

app.on('window-all-closed', () => {
  // On macOS, keep the app alive in the tray
  if (!IS_MAC) app.quit();
});

app.on('before-quit', () => {
  isQuitting = true;
});

app.on('will-quit', () => {
  log('Shutting down spawned processes…');
  if (backendProc)  { backendProc.kill();  backendProc  = null; }
  if (frontendProc) { frontendProc.kill(); frontendProc = null; }
});
