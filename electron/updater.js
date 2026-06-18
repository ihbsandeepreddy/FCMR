/**
 * Auto-updater for SanGir Automations desktop app.
 *
 * Uses electron-updater to check for new releases on the public GitHub releases repo
 * (ihbsandeepreddy/sangir-releases) and installs them on restart.
 */

const { autoUpdater } = require("electron-updater");

const updateLogger = {
  log: (...args) => console.log("[updater]", ...args),
  error: (...args) => console.error("[updater]", ...args),
};

/**
 * Initialize the auto-updater.
 */
function initUpdater() {
  // Configure update source
  autoUpdater.owner = "ihbsandeepreddy";
  autoUpdater.repo = "sangir-releases";
  autoUpdater.channel = "latest";

  // Log events
  autoUpdater.on("checking-for-update", () => {
    updateLogger.log("Checking for updates...");
  });

  autoUpdater.on("update-available", (info) => {
    updateLogger.log(`Update available: ${info.version}`);
  });

  autoUpdater.on("update-not-available", () => {
    updateLogger.log("App is up to date");
  });

  autoUpdater.on("error", (err) => {
    updateLogger.error(`Update error: ${err}`);
  });

  autoUpdater.on("download-progress", (progress) => {
    updateLogger.log(
      `Downloading update: ${Math.round(progress.percent)}% (${progress.transferred}/${progress.total} bytes)`
    );
  });

  autoUpdater.on("update-downloaded", (info) => {
    updateLogger.log(
      `Update downloaded: ${info.version}. Install on next restart.`
    );

    // Prompt user to restart and install
    const { dialog, app } = require("electron");
    dialog
      .showMessageBox({
        type: "info",
        title: "Update Available",
        message: `Version ${info.version} is ready to install.`,
        detail: "The app will update on the next restart.",
        buttons: ["Restart Now", "Later"],
      })
      .then(({ response }) => {
        if (response === 0) {
          autoUpdater.quitAndInstall();
        }
      });
  });

  // Check for updates every 12 hours, or on startup
  autoUpdater.checkForUpdatesAndNotify();
  setInterval(() => {
    autoUpdater.checkForUpdatesAndNotify();
  }, 12 * 60 * 60 * 1000);
}

module.exports = { initUpdater };
