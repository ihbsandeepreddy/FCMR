/**
 * Electron main process for SanGir Automations.
 *
 * Spawns the FastAPI backend, waits for it to be ready, then opens a BrowserWindow.
 * Handles app lifecycle (quit, window closed, etc.).
 */

const { app, BrowserWindow, Menu } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const axios = require("axios");
const { initUpdater } = require("./updater");

let mainWindow;
let backendProcess;
const BACKEND_PORT = 8765;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const MAX_RETRIES = 30; // 30 * 1 sec = 30 sec timeout

/**
 * Spawn the FastAPI backend process.
 */
function spawnBackend() {
  console.log("[Electron] Spawning backend...");

  // In production (packaged), run the frozen .exe from resources
  // In development, run via Python
  const isDev = !app.isPackaged;
  const backendExe = isDev
    ? "python"
    : path.join(process.resourcesPath, "sangir-backend", "sangir-backend.exe");

  // desktop_backend.py lives at the repo root (one level up from electron/)
  const repoRoot = path.join(__dirname, "..");
  const args = isDev ? ["desktop_backend.py"] : [];
  const env = { ...process.env, FCMR_BACKEND_PORT: String(BACKEND_PORT) };

  backendProcess = spawn(backendExe, args, {
    env,
    stdio: "inherit", // Show backend logs in console
    cwd: isDev ? repoRoot : undefined,
  });

  backendProcess.on("error", (err) => {
    console.error("[Electron] Backend spawn error:", err);
  });

  backendProcess.on("exit", (code, signal) => {
    console.log(`[Electron] Backend exited (code: ${code}, signal: ${signal})`);
  });
}

/**
 * Wait for the backend to be ready (health check).
 */
async function waitForBackend(retries = MAX_RETRIES) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await axios.get(BACKEND_URL, { timeout: 1000 });
      if (response.status === 200) {
        console.log("[Electron] Backend is ready");
        return true;
      }
    } catch (err) {
      console.log(`[Electron] Backend not ready (attempt ${i + 1}/${retries})`);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  throw new Error(
    `Backend did not respond after ${retries} seconds. Check logs.`
  );
}

/**
 * Create the BrowserWindow and load the backend URL.
 */
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
    icon: path.join(__dirname, "..", "build", "icon.png"), // Add icon later
  });

  mainWindow.loadURL(BACKEND_URL);

  // Open DevTools in development
  if (!app.isPackaged) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

/**
 * App event handlers.
 */
app.on("ready", async () => {
  try {
    spawnBackend();
    await waitForBackend();
    createWindow();

    // Initialize auto-updater
    initUpdater();

    // Create a simple app menu
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
                  "Deterministic audit analytics for NBFC loan portfolios.\nLocal processing, zero cloud uploads.",
              });
            },
          },
        ],
      },
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
  } catch (err) {
    console.error("[Electron] Startup failed:", err);
    const { dialog } = require("electron");
    dialog.showErrorBox(
      "Startup Error",
      `Failed to start SanGir Automations:\n${err.message}`
    );
    app.quit();
  }
});

app.on("window-all-closed", () => {
  // On macOS, apps typically stay active until the user quits explicitly
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  // Kill the backend process on app quit
  if (backendProcess) {
    console.log("[Electron] Terminating backend...");
    backendProcess.kill();
  }
});

// Prevent multiple app instances
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}
