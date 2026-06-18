/**
 * Preload script for Electron (sandboxed context).
 * Exposes minimal API to the renderer process.
 */

const { contextBridge, app } = require("electron");

contextBridge.exposeInMainWorld("sangir", {
  appVersion: app.getVersion(),
  isPackaged: app.isPackaged,
  platform: process.platform,
});
