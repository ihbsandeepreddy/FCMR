/**
 * Electron main process for SanGir Automations.
 *
 * Robustness improvements over the basic version:
 *  - Per-user data dir (no admin needed)
 *  - Port auto-selection: tries 8765, then scans for a free port
 *  - 90-second backend startup timeout (accommodates slow/old laptops)
 *  - Backend stdout/stderr captured to a log file users can share
 *  - Startup error dialog shows the log path for easy debugging
 */

const { app, BrowserWindow, Menu, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const { spawn } = require("child_process");
const axios = require("axios");
const { initUpdater } = require("./updater");

let mainWindow;
let backendProcess;
let BACKEND_PORT = 8765;
const MAX_RETRIES = 90; // 90 × 1 s = 90 s — gives slow laptops more headroom

// Log file in the user's AppData so users can find and share it easily.
const LOG_DIR = path.join(app.getPath("userData"), "logs");
const BACKEND_LOG = path.join(LOG_DIR, "backend.log");

function ensureLogDir() {
  try { fs.mkdirSync(LOG_DIR, { recursive: true }); } catch (_) {}
}

function writeLog(line) {
  try {
    fs.appendFileSync(BACKEND_LOG, `[${new Date().toISOString()}] ${line}\n`);
  } catch (_) {}
}

/** Find a free TCP port starting from `start`. */
function findFreePort(start) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", () => {
      // Port busy — try next one
      findFreePort(start + 1).then(resolve).catch(reject);
    });
    server.listen(start, "127.0.0.1", () => {
      server.close(() => resolve(start));
    });
  });
}

async function spawnBackend() {
  ensureLogDir();
  writeLog("=== SanGir Automations starting ===");

  // Find a free port (prefer 8765, fall back automatically)
  BACKEND_PORT = await findFreePort(8765);
  writeLog(`Using port ${BACKEND_PORT}`);

  const isDev = !app.isPackaged;
  const backendExe = isDev
    ? "python"
    : path.join(process.resourcesPath, "sangir-backend", "sangir-backend.exe");

  const repoRoot = path.join(__dirname, "..");
  const args = isDev ? [path.join(repoRoot, "desktop_backend.py")] : [];
  const env = {
    ...process.env,
    FCMR_BACKEND_PORT: String(BACKEND_PORT),
    FCMR_APP_VERSION: app.getVersion(),
  };

  writeLog(`Spawning backend: ${backendExe} ${args.join(" ")}`);

  backendProcess = spawn(backendExe, args, {
    env,
    stdio: ["ignore", "pipe", "pipe"],
    cwd: isDev ? repoRoot : undefined,
  });

  // Capture backend output to log file
  backendProcess.stdout.on("data", (data) => {
    const lines = data.toString().trim().split("\n");
    lines.forEach((l) => writeLog(`[backend] ${l}`));
  });
  backendProcess.stderr.on("data", (data) => {
    const lines = data.toString().trim().split("\n");
    lines.forEach((l) => writeLog(`[backend:err] ${l}`));
  });

  backendProcess.on("error", (err) => {
    writeLog(`Backend spawn error: ${err.message}`);
  });

  backendProcess.on("exit", (code, signal) => {
    writeLog(`Backend exited (code=${code}, signal=${signal})`);
  });
}

async function waitForBackend(retries = MAX_RETRIES) {
  const url = `http://127.0.0.1:${BACKEND_PORT}`;
  for (let i = 0; i < retries; i++) {
    try {
      const res = await axios.get(url, { timeout: 2000 });
      if (res.status === 200) {
        writeLog("Backend is ready");
        return true;
      }
    } catch (_) {
      writeLog(`Waiting for backend (${i + 1}/${retries})…`);
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  throw new Error(
    `Backend did not respond after ${retries} seconds.\n\nLog file: ${BACKEND_LOG}`
  );
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
    // icon is optional — missing file is silently ignored
    ...(fs.existsSync(path.join(__dirname, "..", "build", "icon.png"))
      ? { icon: path.join(__dirname, "..", "build", "icon.png") }
      : {}),
  });

  mainWindow.loadURL(`http://127.0.0.1:${BACKEND_PORT}`);

  if (!app.isPackaged) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on("closed", () => { mainWindow = null; });
}

app.on("ready", async () => {
  try {
    await spawnBackend();
    await waitForBackend();
    createWindow();
    initUpdater(mainWindow);

    const template = [
      {
        label: "File",
        submenu: [
          { label: "Exit", accelerator: "CmdOrCtrl+Q", click: () => app.quit() },
        ],
      },
      {
        label: "Help",
        submenu: [
          {
            label: "About",
            click: () => {
              const { dialog } = require("electron");
              dialog.showMessageBox(mainWindow, {
                type: "info",
                title: "About SanGir Automations",
                message: `SanGir Automations v${app.getVersion()}`,
                detail:
                  "Deterministic audit analytics for NBFC loan portfolios.\nLocal processing — zero cloud uploads.",
              });
            },
          },
          {
            label: "Check for Updates",
            click: () => {
              const { autoUpdater } = require("electron-updater");
              autoUpdater.checkForUpdates().catch(() => {});
            },
          },
          { type: "separator" },
          {
            label: "Open Backend Log",
            click: () => { shell.openPath(BACKEND_LOG); },
          },
          {
            label: "Open Update Log",
            click: () => {
              const updateLog = require("path").join(app.getPath("userData"), "logs", "update.log");
              shell.openPath(updateLog);
            },
          },
        ],
      },
    ];

    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  } catch (err) {
    writeLog(`Startup failed: ${err.message}`);
    const { dialog } = require("electron");
    dialog.showErrorBox(
      "Startup Error",
      `Failed to start SanGir Automations:\n${err.message}\n\nShare the log file with support:\n${BACKEND_LOG}`
    );
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    writeLog("Terminating backend…");
    backendProcess.kill();
  }
});

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}
