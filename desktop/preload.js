'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('mnair', {
  onStatus: (cb) => ipcRenderer.on('status', (_, data) => cb(data)),
  onError:  (cb) => ipcRenderer.on('error',  (_, msg)  => cb(msg)),
});
