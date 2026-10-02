"use strict";
// 设置页分块上传器的行为验证：真实执行 upload.js 导出函数，用受控
// bridge 模拟父页响应，核对切片、重试、回执丢失、超时与取消语义。
const assert = require("node:assert/strict");
const { pathToFileURL } = require("node:url");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function makeFile(size, name = "wallpaper.bin") {
  const bytes = new Uint8Array(size);
  for (let index = 0; index < size; index += 1) bytes[index] = index % 251;
  return new File([bytes], name, { lastModified: 4321 });
}

function makeBridge(handlers = {}) {
  const calls = { upload: [], apiGet: [], apiPost: [] };
  return {
    calls,
    async upload(endpoint, file) {
      // 与真实 bridge 一致：只对传入的切片 arrayBuffer，不接触完整上传包。
      const bytes = new Uint8Array(await file.arrayBuffer());
      calls.upload.push({ endpoint, bytes });
      if (handlers.upload) return handlers.upload(endpoint, bytes, calls);
      const index = Number(endpoint.split("/").pop());
      return { next_index: index + 1, received_bytes: 0 };
    },
    async apiGet(endpoint) {
      calls.apiGet.push(endpoint);
      if (handlers.apiGet) return handlers.apiGet(endpoint, calls);
      throw new Error("unexpected apiGet");
    },
    async apiPost(endpoint, body) {
      calls.apiPost.push({ endpoint, body });
      if (handlers.apiPost) return handlers.apiPost(endpoint, body, calls);
      throw new Error(`unexpected apiPost ${endpoint}`);
    },
  };
}

const PROTOCOL = { chunkSize: 64, threshold: 128 };

function makeAppHarness(mod, media, bridge, { realPreview = false } = {}) {
  const source = fs.readFileSync(path.join(path.dirname(process.argv[2]), "app.js"), "utf8");
  const statuses = [], applied = [], listeners = {};
  const previews = [], refreshes = [], warnings = [];
  const context = {
    ...mod, prepareUpload: media.prepareUpload, bridge, AbortController,
    uploading: false, uploadAbortController: null, activeChunkSession: null,
    uploadPageHidden: false, uploadIntents: mod.createUploadIntentStore(),
    uploadPageGeneration: 0, remotePreviewController: null, remotePreviewDataUrl: "",
    PREVIEW_WAIT_MS: 15000,
    uploadProtocol: PROTOCOL, currentConfig: {}, previewOrientation: "landscape",
    mediaPreview: { close() {} }, previewCache: new Map(),
    orientationInputs: { landscape: {}, portrait: {} },
    cancelUploadButton: { addEventListener: (_, handler) => { listeners.cancel = handler; } },
    window: { addEventListener: (event, handler) => { listeners[event] = handler; } },
    setStatus: (text) => statuses.push(text), setBusy() {}, clearLocalPreview() {},
    applyForm: (config) => { assert(config, "成功响应缺 config 时必须先补读"); applied.push(config); },
    loadRemotePreview: async () => {}, notifyPaletteRefresh: () => refreshes.push(true),
    getPreviewBackgroundFilename: (config) => config.filename || "",
    updatePreview: () => previews.push(context.remotePreviewDataUrl),
    console: { warn: (...args) => warnings.push(args) },
  };
  vm.createContext(context);
  vm.runInContext(
    source.slice(source.indexOf("async function uploadBackgroundFiles("),
      source.indexOf("async function selectBackground(")) +
    source.slice(source.indexOf('cancelUploadButton?.addEventListener("click"'),
      source.indexOf("bridge.onContext(")), context,
  );
  if (realPreview) {
    vm.runInContext(source.slice(source.indexOf("async function loadRemotePreview("),
      source.indexOf("function renderList(")), context);
  }
  return { context, statuses, applied, listeners, previews, refreshes, warnings };
}

function loadWithClock() {
  let now = 0, counter = 0;
  const timers = new Map();
  const context = {
    File, DOMException, AbortController, console,
    Date: { now: () => now },
    setTimeout(fn, ms) {
      const id = ++counter;
      timers.set(id, setTimeout(() => {
        if (!timers.has(id)) return;
        timers.delete(id); now += ms; fn();
      }, 0));
      return id;
    },
    clearTimeout(id) { clearTimeout(timers.get(id)); timers.delete(id); },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(process.argv[2], "utf8").replace(/\bexport\s+/g, ""), context);
  return { context, elapsed: () => now };
}

async function main() {
  const mod = await import(pathToFileURL(process.argv[2]).href);
  const {
    parseUploadProtocol,
    requestIdFor,
    createUploadIntentStore,
    uploadPrepared,
    cancelChunkedUpload,
    CHUNK_THRESHOLD,
  } = mod;
  const media = await import(pathToFileURL(path.join(path.dirname(process.argv[2]), "media.js")).href);
  const wallpaper = await import(pathToFileURL(path.join(path.dirname(process.argv[2]), "wallpaper-import.js")).href);

  // 1. 能力探测：只认后端明确声明的协议。
  assert.deepEqual(parseUploadProtocol({
    upload_protocol: { chunked: true, chunk_size: 64, threshold: 128 },
  }), PROTOCOL);
  assert.equal(parseUploadProtocol({}), null);
  assert.equal(parseUploadProtocol({ upload_protocol: { chunked: false } }), null);
  assert.equal(parseUploadProtocol({ upload_protocol: { chunked: true, chunk_size: -1 } }), null);
  assert.equal(parseUploadProtocol(null), null);
  assert.equal(CHUNK_THRESHOLD, 16 * 1024 * 1024);

  // 2. 每次新意图随机；同页结果未知重试保留原身份，确认成功才结束。
  const file = makeFile(300, "a.mp4");
  assert.notEqual(requestIdFor(file, "landscape"), requestIdFor(makeFile(300, "a.mp4"), "landscape"));
  assert.notEqual(requestIdFor(file, "landscape"), requestIdFor(file, "portrait"));
  assert.notEqual(requestIdFor(file, "landscape"), requestIdFor(makeFile(301, "a.mp4"), "landscape"));
  {
    const store = createUploadIntentStore();
    const first = store.acquire(file, "landscape");
    first.uploadId = "pending";
    assert.equal(store.acquire(makeFile(300, "a.mp4"), "landscape"), first);
    store.finish(file, "landscape", first);
    const again = store.acquire(file, "landscape");
    assert.notEqual(again.requestId, first.requestId, "删除后再次上传属于新意图");
    assert.equal(again.uploadId, undefined);
  }

  // 3. 小包（低于阈值）即使有能力也走旧接口，不创建分块会话。
  {
    const bridge = makeBridge({
      upload: () => ({ config: { ok: 1 }, background_image: "small.png" }),
    });
    const result = await uploadPrepared(bridge, makeFile(100), "portrait", {
      protocol: PROTOCOL, requestId: "r1",
    });
    assert.equal(result.background_image, "small.png");
    assert.equal(bridge.calls.upload.length, 1);
    assert.equal(bridge.calls.upload[0].endpoint, "upload-background/portrait");
    assert.equal(bridge.calls.upload[0].bytes.length, 100);
    assert.equal(bridge.calls.apiPost.length, 0);
  }

  // 4. 能力缺失：小包回退旧接口，大包明确提示刷新/升级，绝不整包上传。
  {
    const bridge = makeBridge({ upload: () => ({ config: {} }) });
    await uploadPrepared(bridge, makeFile(100), "landscape", { requestId: "r1" });
    assert.equal(bridge.calls.upload.length, 1);
    await assert.rejects(
      uploadPrepared(bridge, makeFile(CHUNK_THRESHOLD), "landscape", { requestId: "r2" }),
      /刷新页面或升级插件/,
    );
    assert.equal(bridge.calls.upload.length, 1, "大包不得整包回退");
    assert.equal(bridge.calls.apiPost.length, 0);
  }

  // 5. 大包分块：init 参数正确、按序切片、内容完整、complete 后返回结果。
  {
    const uploaded = [];
    const bridge = makeBridge({
      upload: (endpoint, bytes) => {
        uploaded.push(bytes);
        const index = Number(endpoint.split("/").pop());
        return { next_index: index + 1, received_bytes: uploaded.reduce((sum, b) => sum + b.length, 0) };
      },
      apiPost: (endpoint, body) => {
        if (endpoint === "uploads/init") {
          assert.equal(body.orientation, "portrait");
          assert.equal(body.total_bytes, 200);
          assert.equal(body.client_request_id, "req-big");
          return { upload_id: "u1", chunk_size: 64, next_index: 0, received_bytes: 0 };
        }
        if (endpoint === "uploads/u1/complete") return { state: "committed", result: { background_image: "big.mp4", config: {} } };
        throw new Error(endpoint);
      },
    });
    const progress = [];
    const result = await uploadPrepared(bridge, makeFile(200), "portrait", {
      protocol: PROTOCOL, requestId: "req-big", onProgress: (p) => progress.push(p),
    });
    assert.equal(result.background_image, "big.mp4");
    assert.deepEqual(uploaded.map((b) => b.length), [64, 64, 64, 8]);
    const joined = Buffer.concat(uploaded.map((b) => Buffer.from(b)));
    assert.deepEqual(new Uint8Array(joined), new Uint8Array(await makeFile(200).arrayBuffer()));
    assert.equal(progress.length, 4);
    assert.equal(progress.at(-1).receivedBytes, 200);
  }

  // 6. 块回执丢失：status 显示已推进则不重发，从下一块继续。
  {
    const uploadedIndexes = [];
    const bridge = makeBridge({
      upload: (endpoint) => {
        const index = Number(endpoint.split("/").pop());
        uploadedIndexes.push(index);
        if (index === 0) throw new Error("network reset");
        return { next_index: index + 1, received_bytes: (index + 1) * 64 };
      },
      apiGet: () => ({ state: "receiving", next_index: 1, received_bytes: 64 }),
      apiPost: (endpoint) => endpoint === "uploads/init"
        ? { upload_id: "u2", chunk_size: 64, next_index: 0, received_bytes: 0 }
        : { state: "committed", result: { background_image: "x.png", config: {} } },
    });
    await uploadPrepared(bridge, makeFile(192), "landscape", { protocol: PROTOCOL, requestId: "r" });
    assert.deepEqual(uploadedIndexes, [0, 1, 2], "块 0 已被服务器确认，不得重发");
  }

  // 7. 块失败且服务器未推进：重发同一切片，有限重试后成功。
  {
    const attempts = [];
    const bridge = makeBridge({
      upload: (endpoint) => {
        const index = Number(endpoint.split("/").pop());
        attempts.push(index);
        if (attempts.length === 1) throw new Error("network reset");
        return { next_index: index + 1, received_bytes: (index + 1) * 64 };
      },
      apiGet: () => ({ state: "receiving", next_index: 0, received_bytes: 0 }),
      apiPost: (endpoint) => endpoint === "uploads/init"
        ? { upload_id: "u3", chunk_size: 64, next_index: 0, received_bytes: 0 }
        : { state: "committed", result: { background_image: "x.png", config: {} } },
    });
    await uploadPrepared(bridge, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "r" });
    assert.deepEqual(attempts, [0, 0, 1], "未推进时重发同一块");
  }

  // 8. 块连续失败：最多 3 次总尝试后报错，不无限循环。
  {
    let attempts = 0;
    const bridge = makeBridge({
      upload: () => { attempts += 1; throw new Error("network reset"); },
      apiGet: () => ({ state: "receiving", next_index: 0, received_bytes: 0 }),
      apiPost: () => ({ upload_id: "u4", chunk_size: 64, next_index: 0, received_bytes: 0 }),
    });
    await assert.rejects(
      uploadPrepared(bridge, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "r" }),
      /分块上传失败/,
    );
    assert.equal(attempts, 3);
  }

  // 9. complete 响应丢失：轮询原会话状态拿到成功结果，绝不新建会话重传。
  {
    let completeCalls = 0;
    let statusCalls = 0;
    let initCalls = 0;
    const bridge = makeBridge({
      upload: (endpoint) => ({ next_index: Number(endpoint.split("/").pop()) + 1, received_bytes: (Number(endpoint.split("/").pop()) + 1) * 64 }),
      apiGet: () => {
        statusCalls += 1;
        return statusCalls === 1
          ? { state: "processing" }
          : { state: "committed", result: { background_image: "lost.png", config: {} } };
      },
      apiPost: (endpoint) => {
        if (endpoint === "uploads/init") { initCalls += 1; return { upload_id: "u5", chunk_size: 64, next_index: 0, received_bytes: 0 }; }
        completeCalls += 1;
        // 前两次 complete 响应都丢失；状态轮询第二次返回已入库。
        if (completeCalls <= 2) throw new Error("response lost");
        return { state: "processing" };
      },
    });
    const result = await uploadPrepared(bridge, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "r" });
    assert.equal(result.background_image, "lost.png");
    assert.equal(initCalls, 1, "不得新建会话");
  }

  // 10. 断点继续：init 返回已确认位置，从该下一块开始。
  {
    const indexes = [];
    const bridge = makeBridge({
      upload: (endpoint) => {
        indexes.push(Number(endpoint.split("/").pop()));
        return { next_index: Number(endpoint.split("/").pop()) + 1, received_bytes: 128 };
      },
      apiPost: (endpoint) => endpoint === "uploads/init"
        ? { upload_id: "u6", chunk_size: 64, next_index: 1, received_bytes: 64 }
        : { state: "committed", result: { background_image: "x.png", config: {} } },
    });
    await uploadPrepared(bridge, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "r" });
    assert.deepEqual(indexes, [1]);
  }

  // 11. 本地超时只停止本地等待：迟到响应不再驱动新分块。
  {
    let uploadCalls = 0;
    const bridge = makeBridge({
      upload: async () => {
        uploadCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 250));
        return { next_index: 1, received_bytes: 64 };
      },
      apiGet: () => new Promise(() => {}),
      apiPost: (endpoint) => endpoint === "uploads/init"
        ? { upload_id: "u7", chunk_size: 64, next_index: 0, received_bytes: 0 }
        : new Promise(() => {}),
    });
    await assert.rejects(
      uploadPrepared(bridge, makeFile(192), "landscape", {
        protocol: PROTOCOL, requestId: "r", bridgeTimeout: 60,
      }),
      /超时|失败/,
    );
    // 重试本身合理发生；关键是流程废弃后，仍在途的迟到回调不得再启动新块。
    const callsAfterError = uploadCalls;
    await new Promise((resolve) => setTimeout(resolve, 400));
    assert.equal(uploadCalls, callsAfterError, "超时后迟到回调不得启动新块");
  }

  // 12. 本地取消：abort 后停止队列。
  {
    let uploadCalls = 0;
    const controller = new AbortController();
    const bridge = makeBridge({
      upload: async () => {
        uploadCalls += 1;
        controller.abort();
        return { next_index: 1, received_bytes: 64 };
      },
      apiPost: (endpoint) => endpoint === "uploads/init"
        ? { upload_id: "u8", chunk_size: 64, next_index: 0, received_bytes: 0 }
        : { state: "cancelled" },
    });
    await assert.rejects(
      uploadPrepared(bridge, makeFile(320), "landscape", {
        protocol: PROTOCOL, requestId: "r", signal: controller.signal,
      }),
      (error) => error.name === "AbortError",
    );
    assert.equal(uploadCalls, 1, "取消后不得继续发送后续块");
  }

  // 13. 旧接口失败（如 413/超时/鉴权）不触发任何分块回退。
  {
    const bridge = makeBridge({
      upload: () => { throw new Error("Request failed with status code 413"); },
    });
    await assert.rejects(
      uploadPrepared(bridge, makeFile(100), "landscape", { protocol: PROTOCOL, requestId: "r" }),
      /413/,
    );
    assert.equal(bridge.calls.apiPost.length, 0, "旧接口失败不得转入分块");
  }

  // 14. 服务端入库失败：抛出服务端中文错误。
  {
    const bridge = makeBridge({
      upload: (endpoint) => ({ next_index: Number(endpoint.split("/").pop()) + 1, received_bytes: 64 }),
      apiPost: (endpoint) => endpoint === "uploads/init"
        ? { upload_id: "u9", chunk_size: 64, next_index: 0, received_bytes: 0 }
        : { state: "failed", error: "素材内容为空或格式不支持；支持图片、MP4、WebM 和 SVG。" },
    });
    await assert.rejects(
      uploadPrepared(bridge, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "r" }),
      /格式不支持/,
    );
  }

  // 15. 取消返回真实回执；失联不能宣称已停止。
  {
    const bridge = makeBridge({
      apiPost: (endpoint) => { if (endpoint.includes("cancel")) return { state: "cancelled" }; throw new Error(endpoint); },
    });
    assert.equal((await cancelChunkedUpload(bridge, "u10")).state, "cancelled");
    assert.deepEqual(bridge.calls.apiPost.map((c) => c.endpoint), ["uploads/u10/cancel"]);
    const failing = makeBridge({ apiPost: () => { throw new Error("gone"); } });
    assert.equal(await cancelChunkedUpload(failing, "u11"), null);
    await cancelChunkedUpload(failing, "");
  }

  // 16. 已取消的入口不发请求；真实 PNG 头读取中取消也不进入 bridge。
  {
    const controller = new AbortController();
    controller.abort();
    const bridge = makeBridge();
    for (const size of [100, 128]) {
      await assert.rejects(uploadPrepared(bridge, makeFile(size), "landscape", {
        protocol: PROTOCOL, requestId: "cancelled", signal: controller.signal,
      }), error => error.name === "AbortError");
    }
    assert.equal(bridge.calls.upload.length + bridge.calls.apiPost.length, 0);
    const preparing = new AbortController();
    const file = { name: "head.png", size: 10, slice() {
      return { async arrayBuffer() {
        preparing.abort();
        return Uint8Array.from([137,80,78,71,13,10,26,10]).buffer;
      } };
    } };
    await assert.rejects(media.prepareUpload(file, preparing.signal), error => error.name === "AbortError");
  }

  // 17. 退避期间取消不再重发块；同步取消后 Promise 迟到拒绝已被消费。
  {
    const unhandled = [];
    const onUnhandled = (error) => unhandled.push(error);
    process.on("unhandledRejection", onUnhandled);
    try {
      const controller = new AbortController();
      let timer;
      const bridge = makeBridge({
        upload: () => { throw new Error("lost"); },
        apiPost: (endpoint) => endpoint === "uploads/init"
          ? { upload_id: "backoff", chunk_size: 64, state: "receiving" }
          : { state: "cancelled" },
        apiGet: () => {
          timer = setTimeout(() => controller.abort(), 20);
          return { state: "receiving", next_index: 0 };
        },
      });
      await assert.rejects(uploadPrepared(bridge, makeFile(128), "landscape", {
        protocol: PROTOCOL, requestId: "backoff", signal: controller.signal,
      }), error => error.serverCancelled);
      clearTimeout(timer);
      assert.equal(bridge.calls.upload.length, 1);
      const late = new AbortController();
      await assert.rejects(uploadPrepared({
        upload() {
          late.abort();
          return new Promise((_, reject) => setTimeout(() => reject(new Error("late failure")), 10));
        },
      }, makeFile(10), "landscape", { signal: late.signal }),
      error => error.name === "AbortError");
      await new Promise(resolve => setTimeout(resolve, 30));
      assert.deepEqual(unhandled, []);
    } finally { process.off("unhandledRejection", onUnhandled); }
  }

  // 18. 真正 180 秒截止线：每次请求只用剩余预算，最多三次连续失败。
  {
    const clock = loadWithClock();
    let complete = 0, status = 0;
    const session = {};
    await assert.rejects(clock.context.uploadChunked({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return Promise.resolve({
          upload_id: "deadline", chunk_size: 64, next_index: 2,
          received_bytes: 128, state: "receiving",
        });
        complete += 1; return new Promise(() => {});
      },
      apiGet() { status += 1; return new Promise(() => {}); },
    }, makeFile(128), "landscape", {
      protocol: PROTOCOL, requestId: "deadline", session,
    }), error => error.name === "UploadResultUnknown");
    assert.equal(clock.elapsed(), 180000);
    assert.equal(complete, 1);
    assert.equal(status, 2);
    assert.equal(session.uploadId, "deadline", "预算耗尽仍保留原身份");
    let failures = 0;
    const failedClock = loadWithClock();
    await assert.rejects(failedClock.context.uploadChunked({
      apiPost() { throw new Error("不得重新 init/complete"); },
      apiGet() { failures += 1; return Promise.reject(new Error("Request failed with status code 404")); },
    }, makeFile(128), "landscape", {
      protocol: PROTOCOL, requestId: "same", session: { uploadId: "old", state: "processing" },
    }), error => error.name === "UploadResultUnknown");
    assert.equal(failures, 1, "原身份恢复失败应立即返回，不依赖中文错误文字");
    const losingClock = loadWithClock();
    let lostQueries = 0, lostComplete = 0;
    await assert.rejects(losingClock.context.uploadChunked({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return Promise.resolve({
          upload_id: "lost", chunk_size: 64, next_index: 2,
          received_bytes: 128, state: "receiving",
        });
        lostComplete += 1;
        return Promise.reject(new Error("network"));
      },
      apiGet() {
        lostQueries += 1;
        return Promise.reject(new Error("Request failed with status code 404"));
      },
    }, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "lost" }),
    error => error.name === "UploadResultUnknown");
    assert.equal(lostComplete, 1);
    assert.equal(lostQueries, 2, "连续三次确认失败即停止，不按错误文字无限请求");
    const processingClock = loadWithClock();
    let polling = 0;
    await assert.rejects(processingClock.context.uploadChunked({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return Promise.resolve({
          upload_id: "processing-deadline", chunk_size: 64, state: "processing",
        });
        throw new Error("processing 不得重发 complete");
      },
      apiGet() { polling += 1; return Promise.resolve({ state: "processing" }); },
    }, makeFile(128), "landscape", { protocol: PROTOCOL, requestId: "p" }),
    error => error.name === "UploadResultUnknown");
    assert.equal(processingClock.elapsed(), 180000);
    assert.equal(polling, 180);
  }

  // 19. 普通上传的真实控制函数：成功后重选同文件创建新意图；无 config 补读。
  {
    let initCount = 0;
    const ids = [];
    const bridge = makeBridge({
      apiPost(endpoint, body) {
        if (endpoint === "uploads/init") {
          ids.push(body.client_request_id);
          return { upload_id: `new-${++initCount}`, chunk_size: 64, state: "receiving", next_index: 2, received_bytes: 128 };
        }
        return { state: "committed", result: { background_image: "new.png" } };
      },
      apiGet: () => ({ latest: true }),
    });
    const app = makeAppHarness(mod, media, bridge);
    app.context.prepareUpload = async file => file;
    const file = makeFile(128);
    assert.equal(await app.context.uploadBackgroundFiles([file], "landscape"), true);
    assert.equal(await app.context.uploadBackgroundFiles([file], "landscape"), true);
    assert.equal(initCount, 2);
    assert.notEqual(ids[0], ids[1]);
    assert.equal(app.applied.at(-1).latest, true);
  }

  // 20. 真实 app 取消 processing：最终成功刷新图库，并停止后续批量队列。
  {
    let app;
    const bridge = makeBridge({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return {
          upload_id: "cancel-processing", state: "receiving", chunk_size: 64,
          next_index: 2, received_bytes: 128,
        };
        if (endpoint.endsWith("/complete")) {
          app.listeners.cancel();
          return { state: "processing" };
        }
        return { state: "processing" };
      },
      apiGet: () => ({ state: "committed", result: { config: { saved: true }, background_image: "saved.mp4" } }),
    });
    app = makeAppHarness(mod, media, bridge);
    app.context.prepareUpload = async file => file;
    assert.equal(await app.context.uploadBackgroundFiles([makeFile(128), makeFile(128, "second")], "landscape"), true);
    assert.equal(bridge.calls.apiPost.filter(c => c.endpoint === "uploads/init").length, 1);
    assert.equal(app.applied.at(-1).saved, true);
    assert(app.statuses.some(text => text.includes("后续素材已停止")));
    assert(!app.statuses.some(text => text === "已取消上传"));
    // Wallpaper Engine 使用同一控制函数，实际成功后必须标记 imported。
    const item = { file: makeFile(128), state: "ready" };
    assert.equal(await wallpaper.importWallpaperItem(item, "portrait", async (file, orientation) => {
      if (!await app.context.uploadBackgroundFiles([file], orientation)) throw new Error("upload failed");
    }), true);
    assert.equal(item.state, "imported");
  }

  // 21. 结果未知后重试核对原 uploadId，不重新 init 或传块。
  {
    const session = { uploadId: "known", chunkSize: 64, state: "processing" };
    const bridge = makeBridge({
      apiGet: () => ({ state: "committed", result: { config: {}, background_image: "known.png" } }),
    });
    const result = await uploadPrepared(bridge, makeFile(128), "landscape", {
      protocol: PROTOCOL, requestId: "same-intent", session,
    });
    assert.equal(result.background_image, "known.png");
    assert.equal(bridge.calls.apiPost.length + bridge.calls.upload.length, 0);
  }

  // 22. 真实上游 bridge：取消文件准备后没有父页请求；每次只转换切片。
  {
    const bridgePath = process.argv[3];
    if (bridgePath) {
      let onMessage;
      const sent = [];
      const fakeWindow = {
        location: { origin: "https://palette.test" },
        addEventListener(event, handler) { if (event === "message") onMessage = handler; },
      };
      fakeWindow.parent = {
        postMessage(message) {
          if (message.kind !== "request") return;
          sent.push(message);
          let data;
          if (message.endpoint === "uploads/init") {
            data = { upload_id: "real-bridge", state: "receiving", chunk_size: 64 };
          } else if (message.action === "files:upload") {
            const index = Number(message.endpoint.split("/").pop());
            data = { next_index: index + 1, received_bytes: (index + 1) * 64 };
          } else {
            data = { state: "committed", result: { config: {}, background_image: "real.png" } };
          }
          queueMicrotask(() => onMessage({
            source: fakeWindow.parent, origin: "https://palette.test",
            data: { channel: "astrbot-plugin-page", kind: "response",
              requestId: message.requestId, ok: true, data },
          }));
        },
      };
      const context = { window: fakeWindow, document: { documentElement: { setAttribute() {} } }, console };
      vm.createContext(context);
      vm.runInContext(fs.readFileSync(bridgePath, "utf8"), context);
      const realBridge = fakeWindow.AstrBotPluginPage;
      const app = makeAppHarness(mod, media, realBridge);
      let releaseHead;
      const head = new Promise(resolve => { releaseHead = resolve; });
      const file = {
        name: "preparing.png", size: 100, lastModified: 1,
        slice() { return { arrayBuffer: () => head }; },
      };
      const uploading = app.context.uploadBackgroundFiles([file], "landscape");
      app.listeners.cancel();
      releaseHead(Uint8Array.from([137,80,78,71,13,10,26,10]).buffer);
      assert.equal(await uploading, false);
      assert.equal(sent.length, 0, "准备中取消不能启动真实父页 bridge 请求");
      const sliced = makeFile(192);
      sliced.arrayBuffer = () => { throw new Error("不得转换完整包"); };
      const result = await uploadPrepared(realBridge, sliced, "landscape", {
        protocol: PROTOCOL, requestId: "real",
      });
      assert.equal(result.background_image, "real.png");
      assert.deepEqual(sent.filter(c => c.action === "files:upload").map(c => c.fileBuffer.byteLength), [64,64,64]);
    }
  }

  // 23. 取消回执丢失且服务器仍 receiving：不得发 complete，也不误报已取消。
  {
    const controller = new AbortController();
    let completes = 0;
    const bridge = makeBridge({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return {
          upload_id: "cancel-lost", state: "receiving", chunk_size: 64,
        };
        if (endpoint.endsWith("/cancel")) throw new Error("cancel response lost");
        completes += 1;
        return { state: "processing" };
      },
      upload() { controller.abort(); return new Promise(() => {}); },
      apiGet: () => ({ state: "receiving", next_index: 0 }),
    });
    await assert.rejects(uploadPrepared(bridge, makeFile(128), "landscape", {
      protocol: PROTOCOL, requestId: "cancel-lost", signal: controller.signal,
    }), error => error.name === "UploadResultUnknown");
    assert.equal(completes, 0);
  }

  // 24. 真实 app 网络失败后重试保留同一意图、已准备包和 uploadId。
  {
    let fail = true, prepares = 0;
    const bridge = makeBridge({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return {
          upload_id: "app-retry", state: "receiving", chunk_size: 64,
        };
        return { state: "committed", result: { background_image: "retry.png", config: {} } };
      },
      upload(endpoint) {
        if (fail) throw new Error("network");
        return { next_index: Number(endpoint.split("/").pop()) + 1, received_bytes: 128 };
      },
      apiGet: () => ({ state: "receiving", chunk_size: 64, next_index: 0 }),
    });
    const app = makeAppHarness(mod, media, bridge);
    app.context.prepareUpload = async file => { prepares += 1; return file; };
    const file = makeFile(128);
    assert.equal(await app.context.uploadBackgroundFiles([file], "landscape"), false);
    fail = false;
    assert.equal(await app.context.uploadBackgroundFiles([makeFile(128)], "landscape"), true);
    assert.equal(prepares, 1, "结果未知重试不能重新打包改变参数");
    assert.equal(bridge.calls.apiPost.filter(c => c.endpoint === "uploads/init").length, 1);
  }

  // 25. pagehide 后旧结果不回填，真实 WE 重试查询原成功会话，不重复入库。
  {
    let app, finish;
    const waiting = new Promise(resolve => { finish = resolve; });
    const bridge = makeBridge({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return {
          upload_id: "pagehide", state: "receiving", chunk_size: 64,
          next_index: 2, received_bytes: 128,
        };
        if (endpoint.endsWith("/complete")) {
          app.listeners.pagehide();
          app.listeners.pageshow();
          return { state: "processing" };
        }
        return { state: "processing" };
      },
      apiGet: () => waiting,
    });
    app = makeAppHarness(mod, media, bridge);
    app.context.prepareUpload = async file => file;
    const item = { file: makeFile(128), state: "ready" };
    const importFile = async (file, orientation) => {
      if (!await app.context.uploadBackgroundFiles([file], orientation)) {
        throw new Error("本次结果未交付页面，可重试确认原上传");
      }
    };
    const uploading = wallpaper.importWallpaperItem(item, "landscape", importFile);
    finish({ state: "committed", result: { config: {}, background_image: "late.png" } });
    assert.equal(await uploading, false);
    assert.equal(item.state, "failed");
    assert.equal(app.applied.length, 0);
    assert.equal(bridge.calls.apiPost.filter(c => c.endpoint === "uploads/init").length, 1);
    assert.equal(await wallpaper.importWallpaperItem(item, "landscape", importFile), true);
    assert.equal(item.state, "imported");
    assert.equal(bridge.calls.apiPost.filter(c => c.endpoint === "uploads/init").length, 1);
    assert.equal(bridge.calls.apiPost.filter(c => c.endpoint.endsWith("/complete")).length, 1);
    assert.equal(app.applied.length, 1);
  }

  // 26. 批量部分成功后取消已发小包：只停止本地等待，明确提示核对服务器结果。
  {
    let app, resolveSecond;
    const saved = [];
    const second = new Promise(resolve => { resolveSecond = resolve; });
    const bridge = makeBridge({
      upload(endpoint, bytes, calls) {
        saved.push(calls.upload.length === 1 ? "first.png" : "second.png");
        if (saved.length === 1) return { config: { gallery: [...saved] } };
        app.listeners.cancel();
        return second;
      },
    });
    app = makeAppHarness(mod, media, bridge);
    app.context.prepareUpload = async file => file;
    assert.equal(await app.context.uploadBackgroundFiles([
      makeFile(10, "first.png"), makeFile(10, "second.png"), makeFile(10, "third.png"),
    ], "portrait"), false);
    assert.equal(bridge.calls.upload.length, 2, "取消后停止后续队列");
    assert.deepEqual(saved, ["first.png", "second.png"]);
    assert.deepEqual(app.applied.at(-1).gallery, ["first.png"]);
    assert(app.statuses.at(-1).includes("已停止本地等待，请刷新图库确认服务器结果"));
    assert(!app.statuses.at(-1).includes("已取消上传"));
    resolveSecond({ config: { gallery: [...saved] } });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(app.applied.length, 1, "迟到小包结果不覆盖已提示的未知状态");
  }

  // 27. 部分成功后服务器明确取消分块：仍可以准确报告取消，不误报未知。
  {
    let app;
    const bridge = makeBridge({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return {
          upload_id: "partial-cancel", state: "receiving", chunk_size: 64,
        };
        if (endpoint.endsWith("/cancel")) return { state: "cancelled" };
        throw new Error("取消后不能完成上传");
      },
      upload(endpoint) {
        if (endpoint.startsWith("upload-background/")) return { config: { saved: true } };
        app.listeners.cancel();
        return new Promise(() => {});
      },
    });
    app = makeAppHarness(mod, media, bridge);
    app.context.prepareUpload = async file => file;
    assert.equal(await app.context.uploadBackgroundFiles([
      makeFile(10), makeFile(128, "cancelled.png"), makeFile(10, "next.png"),
    ], "landscape"), false);
    assert(app.statuses.at(-1).includes("已取消上传"));
    assert(!app.statuses.at(-1).includes("核对服务器结果"));
    assert.equal(bridge.calls.upload.length, 2);
  }

  // 28. 真实缩略图等待跨 pagehide：不回填、不清掉原意图，恢复后 WE 核对一次。
  {
    let app, resolveThumbnail, thumbnailCalls = 0;
    const lateThumbnail = new Promise(resolve => { resolveThumbnail = resolve; });
    const committed = { state: "committed", result: { config: { filename: "saved.png" } } };
    const bridge = makeBridge({
      apiPost(endpoint) {
        if (endpoint === "uploads/init") return { upload_id: "preview-stale", ...committed };
        if (endpoint.endsWith("/cancel")) return committed;
        throw new Error("不应重新 complete");
      },
      apiGet(endpoint) {
        if (endpoint.endsWith("/status")) return committed;
        assert.equal(endpoint, "background-thumbnail");
        thumbnailCalls += 1;
        if (thumbnailCalls === 1) return lateThumbnail;
        return { data_url: "data:image/png;base64,current" };
      },
    });
    app = makeAppHarness(mod, media, bridge, { realPreview: true });
    app.context.prepareUpload = async file => file;
    const item = { file: makeFile(128), state: "ready" };
    const importFile = async (file, orientation) => {
      if (!await app.context.uploadBackgroundFiles([file], orientation)) {
        throw new Error("页面已离开，重试核对原上传");
      }
    };
    const uploading = wallpaper.importWallpaperItem(item, "landscape", importFile);
    while (!thumbnailCalls) await new Promise(resolve => setImmediate(resolve));
    app.listeners.pagehide();
    app.listeners.pageshow();
    assert.equal(await uploading, false);
    assert.equal(item.state, "failed");
    const statusCount = app.statuses.length;
    resolveThumbnail({ data_url: "data:image/png;base64,late" });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(app.context.previewCache.size, 0);
    assert.equal(app.previews.length + app.refreshes.length, 0);
    assert.equal(app.statuses.length, statusCount);
    assert.equal(await wallpaper.importWallpaperItem(item, "landscape", importFile), true);
    assert.equal(item.state, "imported");
    assert.equal(bridge.calls.apiPost.filter(c => c.endpoint === "uploads/init").length, 1);
    assert.equal(app.context.remotePreviewDataUrl, "data:image/png;base64,current");
  }

  // 29. 已确认入库后取消辅助预览：立即结束等待，仍交付成功，不变成失败重传。
  {
    let rejectThumbnail, requested = false;
    const pending = new Promise((_, reject) => { rejectThumbnail = reject; });
    const bridge = makeBridge({
      upload: () => ({ config: { filename: "stored.png" } }),
      apiGet() { requested = true; return pending; },
    });
    const app = makeAppHarness(mod, media, bridge, { realPreview: true });
    app.context.prepareUpload = async file => file;
    const uploading = app.context.uploadBackgroundFiles([makeFile(10)], "landscape");
    while (!requested) await new Promise(resolve => setImmediate(resolve));
    app.listeners.cancel();
    assert.equal(await uploading, true);
    assert.equal(app.context.uploading, false);
    assert(app.statuses.at(-1).includes("已加入横屏图库 1 项背景素材"));
    assert(app.statuses.at(-1).includes("后续素材已停止"));
    const unhandled = [];
    const onUnhandled = error => unhandled.push(error);
    process.on("unhandledRejection", onUnhandled);
    try {
      rejectThumbnail(new Error("迟到缩略图失败"));
      await new Promise(resolve => setImmediate(resolve));
      assert.deepEqual(unhandled, []);
      assert.equal(app.context.previewCache.size, 0);
      assert.equal(app.previews.length, 0);
    } finally { process.off("unhandledRejection", onUnhandled); }
  }

  // 30. 真实预览超时有界且迟到不回填；较新预览替代旧请求，缓存命中仍可用。
  {
    let resolveLate;
    const pending = new Promise(resolve => { resolveLate = resolve; });
    const bridge = makeBridge({
      upload: () => ({ config: { filename: "timeout.png" } }),
      apiGet: () => pending,
    });
    const app = makeAppHarness(mod, media, bridge, { realPreview: true });
    app.context.PREVIEW_WAIT_MS = 20;
    app.context.prepareUpload = async file => file;
    assert.equal(await app.context.uploadBackgroundFiles([makeFile(10)], "landscape"), true);
    assert.equal(app.context.uploading, false);
    assert.equal(app.warnings.length, 1);
    const previewCount = app.previews.length;
    resolveLate({ data_url: "data:image/png;base64,late" });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(app.previews.length, previewCount);
    assert.equal(app.context.previewCache.size, 0);

    let resolveOld;
    const old = new Promise(resolve => { resolveOld = resolve; });
    let requested = false;
    const changing = makeBridge({
      apiGet(endpoint, calls) {
        requested = true;
        if (calls.apiGet.length === 1) return old;
        return { data_url: "data:image/png;base64,new" };
      },
    });
    const replacement = makeAppHarness(mod, media, changing, { realPreview: true });
    const stale = replacement.context.loadRemotePreview({ filename: "old.png" });
    while (!requested) await new Promise(resolve => setImmediate(resolve));
    await replacement.context.loadRemotePreview({ filename: "new.png" });
    await stale;
    resolveOld({ data_url: "data:image/png;base64,old" });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(replacement.context.remotePreviewDataUrl, "data:image/png;base64,new");
    assert.deepEqual(replacement.previews, ["data:image/png;base64,new"]);
    await replacement.context.loadRemotePreview({ filename: "new.png" });
    assert.equal(changing.calls.apiGet.length, 2, "有效缓存命中不再请求");
  }

  console.log("行为验证通过");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
