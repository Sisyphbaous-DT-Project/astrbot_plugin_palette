/* 浏览器本地素材缓存：只缓存已通过登录配置确认的素材，和页面内存缓存独立。 */
(function (root, factory) {
  var api = factory();
  root.AstrBotPaletteCache = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  var MAX_BYTES = 1024 * 1024 * 1024;
  var DATABASE_NAME = "astrbot-palette-media";
  var IO_TIMEOUT_MS = 5000;

  function create(root, options) {
    var maxBytes = options && options.maxBytes || MAX_BYTES;
    var databaseName = options && options.databaseName || DATABASE_NAME;
    var connection = null;
    var opening = null;
    var available = false;
    try { available = Boolean(root.indexedDB); } catch (_) {}
    var allowed = new Set();
    var configured = false;

    function open() {
      if (!available) return Promise.resolve(null);
      if (connection) return Promise.resolve(connection);
      if (opening) return opening;
      opening = new Promise(function (resolve) {
        var settled = false;
        var finish = function (db) {
          if (settled) { if (db) db.close(); return; }
          settled = true;
          root.clearTimeout(timer);
          if (!db) available = false;
          connection = db;
          resolve(db);
        };
        var timer = root.setTimeout(function () { finish(null); }, IO_TIMEOUT_MS);
        try {
          var request = root.indexedDB.open(databaseName, 1);
          request.onupgradeneeded = function () {
            var db = request.result;
            db.createObjectStore("metadata", { keyPath: "url" });
            db.createObjectStore("blobs");
            db.createObjectStore("state");
          };
          request.onerror = function () { finish(null); };
          request.onblocked = function () { finish(null); };
          request.onsuccess = function () {
            var db = request.result;
            db.onversionchange = function () {
              db.close();
              connection = null;
              opening = null;
            };
            finish(db);
          };
        } catch (_) { finish(null); }
      });
      return opening;
    }

    async function transaction(stores, action, fallback, signal, timeoutMs) {
      var db = await open();
      if (!db || signal && signal.aborted) return fallback;
      return new Promise(function (resolve) {
        var settled = false;
        var value = fallback;
        var tx;
        var finish = function (result) {
          if (settled) return;
          settled = true;
          root.clearTimeout(timer);
          if (signal) signal.removeEventListener("abort", cancel);
          resolve(result);
        };
        var cancel = function () {
          try { if (tx) tx.abort(); } catch (_) {}
          finish(fallback);
        };
        var timer = root.setTimeout(cancel, timeoutMs || IO_TIMEOUT_MS);
        if (signal) signal.addEventListener("abort", cancel, { once: true });
        try {
          // 事务中只用 IDB 回调串联请求，不跨 await 使事务提前提交。
          tx = db.transaction(stores, "readwrite");
          tx.oncomplete = function () { finish(value); };
          tx.onabort = tx.onerror = function () { finish(fallback); };
          action(tx, function (next) { value = next; });
        } catch (_) { cancel(); }
      });
    }

    function remove(tx, url) {
      tx.objectStore("metadata").delete(url);
      tx.objectStore("blobs").delete(url);
    }

    function setConfig(config) {
      var next = new Set();
      ["background_items", "landscape_background_items", "portrait_background_items"]
        .forEach(function (key) {
          (config[key] || []).forEach(function (item) {
            if (item.url) next.add(item.url);
            if (item.cover_url) next.add(item.cover_url);
          });
        });
      // 当前素材也覆盖旧配置回退，首次升级不要求重新上传或选择。
      ["background", "landscape_background", "portrait_background", "fallback_background"]
        .forEach(function (key) {
          if (config[key + "_url"]) next.add(config[key + "_url"]);
          var media = config[key + "_media"];
          if (media && media.cover_url) next.add(media.cover_url);
        });
      var unchanged = configured && next.size === allowed.size &&
        Array.from(next).every(function (url) { return allowed.has(url); });
      allowed = next;
      configured = true;
      if (unchanged) return Promise.resolve(null);
      return transaction(["metadata", "blobs"], function (tx) {
        var request = tx.objectStore("metadata").getAllKeys();
        request.onsuccess = function () {
          request.result.forEach(function (url) {
            if (!allowed.has(url)) remove(tx, url);
          });
        };
      }, null);
    }

    async function read(url, signal) {
      if (!allowed.has(url)) return { blob: null, epoch: null };
      return transaction(["metadata", "blobs", "state"], function (tx, done) {
        var epoch = tx.objectStore("state").get("epoch");
        epoch.onsuccess = function () {
          var result = { blob: null, epoch: epoch.result || 0 };
          done(result);
          var metadata = tx.objectStore("metadata").get(url);
          metadata.onsuccess = function () {
            if (!metadata.result || !allowed.has(url)) return;
            var entry = metadata.result;
            var request = tx.objectStore("blobs").get(url);
            request.onsuccess = function () {
              var blob = request.result;
              if (!blob || !blob.size || blob.size !== entry.size) {
                remove(tx, url);
                return;
              }
              entry.lastUsed = Date.now();
              tx.objectStore("metadata").put(entry);
              result.blob = blob;
            };
          };
        };
      }, { blob: null, epoch: null }, signal);
    }

    function write(url, blob, epoch, signal) {
      if (epoch === null || !allowed.has(url) || !blob.size) {
        return Promise.resolve(false);
      }
      return transaction(["metadata", "blobs", "state"], function (tx, done) {
        var currentEpoch = tx.objectStore("state").get("epoch");
        currentEpoch.onsuccess = function () {
          // 清理跨标签页生效；旧下载不能在清理之后重新回填。
          if ((currentEpoch.result || 0) !== epoch || !allowed.has(url)) return;
          var entries = tx.objectStore("metadata").getAll();
          entries.onsuccess = function () {
            if (!allowed.has(url)) return;
            // 超预算的单项单独保留，不占普通预算，也不参与普通素材的淘汰。
            var rows = entries.result.filter(function (row) {
              return row.url !== url && row.size <= maxBytes;
            });
            var total = rows.reduce(function (sum, row) { return sum + row.size; },
              blob.size <= maxBytes ? blob.size : 0);
            rows.sort(function (a, b) { return a.lastUsed - b.lastUsed; });
            rows.forEach(function (row) {
              if (total > maxBytes) { remove(tx, row.url); total -= row.size; }
            });
            tx.objectStore("blobs").put(blob, url);
            tx.objectStore("metadata").put({ url: url, size: blob.size, lastUsed: Date.now() });
            done(true);
          };
        };
      }, false, signal, 60000);
    }

    function stats() {
      return transaction(["metadata"], function (tx, done) {
        var request = tx.objectStore("metadata").getAll();
        request.onsuccess = function () {
          done({
            available: true,
            bytes: request.result.reduce(function (sum, row) { return sum + row.size; }, 0),
            count: request.result.length,
            maxBytes: maxBytes,
            budgetBytes: request.result.reduce(function (sum, row) {
              return sum + (row.size <= maxBytes ? row.size : 0);
            }, 0),
            largeBytes: request.result.reduce(function (sum, row) {
              return sum + (row.size > maxBytes ? row.size : 0);
            }, 0),
            largeCount: request.result.filter(function (row) { return row.size > maxBytes; }).length,
          });
        };
      }, { available: false, bytes: 0, count: 0, maxBytes: maxBytes });
    }

    async function clear() {
      var cleared = await transaction(["metadata", "blobs", "state"], function (tx, done) {
        var state = tx.objectStore("state");
        var request = state.get("epoch");
        request.onsuccess = function () {
          state.put((request.result || 0) + 1, "epoch");
          tx.objectStore("metadata").clear();
          tx.objectStore("blobs").clear();
          done(true);
        };
      }, false);
      var result = await stats();
      result.cleared = cleared;
      return result;
    }

    function close() {
      if (connection) connection.close();
      connection = null;
      opening = null;
    }

    return { setConfig: setConfig, read: read, write: write, stats: stats, clear: clear, close: close };
  }

  return { create: create, MAX_BYTES: MAX_BYTES, DATABASE_NAME: DATABASE_NAME };
});
