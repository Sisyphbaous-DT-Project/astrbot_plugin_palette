/* 注入后真实函数行为测试；只模拟 DOM/媒体设备，不替换待测状态逻辑。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { pathToFileURL } = require("node:url");

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.listeners = {};
    this.style = { setProperty(name, value) { this[name] = value; }, removeProperty(name) { delete this[name]; } };
    const names = new Set();
    this.classList = {
      add: (name) => names.add(name), remove: (name) => names.delete(name),
      contains: (name) => names.has(name),
      toggle: (name, value) => value ? names.add(name) : names.delete(name),
    };
    this.readyState = 2;
    this.playCount = 0; this.pauseCount = 0; this.loadCount = 0;
    this.paused = true; this.currentTime = 7;
  }
  appendChild(child) { child.parentNode?.removeChild(child); this.children.push(child); child.parentNode = this; return child; }
  prepend(child) { this.appendChild(child); }
  removeChild(child) { this.children = this.children.filter((item) => item !== child); child.parentNode = null; }
  remove() { this.parentNode?.removeChild(this); }
  contains(child) { return this.children.includes(child); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; if (name === "src") this.src = ""; }
  addEventListener(name, fn) { (this.listeners[name] ||= new Set()).add(fn); }
  removeEventListener(name, fn) { this.listeners[name]?.delete(fn); }
  dispatch(name) { this.listeners[name]?.forEach((fn) => fn({ type: name })); }
  querySelectorAll(selector) {
    return this.children.filter((child) => child.className === "astrbot-palette-background-layer");
  }
  querySelector(selector) { return this.querySelectorAll(selector).find((child) => child.classList.contains("is-active")) || null; }
  play() { this.playCount++; if (this.failPlay) return Promise.reject(new Error("blocked")); this.paused = false; return Promise.resolve(); }
  pause() { this.pauseCount++; this.paused = true; }
  load() { this.loadCount++; }
}

function environment() {
  const body = new Element("body"), root = new Element("html"), head = new Element("head");
  const created = [], revoked = [], requests = [], events = {};
  const timeouts = new Map();
  let timerId = 0;
  let hidden = false, reduced = false, failNextVideo = false, badNextImage = false;
  const document = {
    body, head, documentElement: root,
    get hidden() { return hidden; }, get visibilityState() { return hidden ? "hidden" : "visible"; },
    createElement(tag) {
      const element = new Element(tag);
      if (tag === "video") { element.failPlay = failNextVideo; failNextVideo = false; }
      created.push(element); return element;
    },
    getElementById(id) { return [...body.children, ...head.children].find((element) => element.id === id) || null; },
    querySelector() { return null; },
    addEventListener(name, fn) { events[name] = fn; },
  };
  const storage = new Map();
  const window = {
    document, localStorage: {
      getItem: (key) => storage.get(key) || "", setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    innerWidth: 1000, innerHeight: 700,
    matchMedia(query) { return { matches: query.includes("reduced-motion") && reduced, addEventListener() {} }; },
    addEventListener(name, fn) { events[name] = fn; },
    setTimeout(fn, delay) {
      if (delay < 1000) return setTimeout(fn, delay);
      const id = --timerId;
      timeouts.set(id, { fn, delay });
      return id;
    },
    clearTimeout(id) { timeouts.delete(id); clearTimeout(id); },
    setInterval() { return 0; }, clearInterval,
    requestAnimationFrame(fn) { queueMicrotask(fn); },
    getComputedStyle() { return { getPropertyValue() { return ""; } }; },
  };
  class Image {
    set src(value) { queueMicrotask(() => badNextImage ? this.onerror?.() : this.onload?.()); }
    decode() { return Promise.resolve(); }
  }
  let objectCounter = 0;
  const context = {
    document, window, self: window, Image, navigator: {}, console,
    URL: { createObjectURL() { return `blob:test-${++objectCounter}`; }, revokeObjectURL(url) { revoked.push(url); } },
    AbortController, Blob, DOMException,
    setTimeout: window.setTimeout, clearTimeout: window.clearTimeout,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, headers: { get() { return ""; } }, blob: async () => new Blob(["media"]) };
    },
  };
  let script = fs.readFileSync(process.argv[2], "utf8");
  script = script.replace(
    '    setupPaletteSync();\n    bootstrapRecommendedDarkTheme();\n    refreshPalette({ allowInitialRandom: true });',
    `window.test = {
      apply: applyDirectionalBackground, inactive: setInactive,
      visibility: syncBackgroundVideoVisibility,
      refresh: refreshPalette,
      rotate: runRotationTick,
      acquireTestLeadership: function() { rotationLeadership = {mode: "lease", nonce: "test"}; },
      fetchBackground, revoke: revokeObjectUrls,
      release: function(url) { unmarkObjectUrlInFlight(url); evictObjectUrlCache(); },
      state: function() { return {
        url: currentBackgroundUrl, status: currentMediaStatus,
        objectUrl: currentObjectUrl, cache: backgroundObjectUrlCache.size,
        bytes: backgroundCacheTotalBytes,
        inflight: Object.keys(backgroundInFlightObjectUrls).length,
        inuse: Object.keys(backgroundInUseObjectUrls).length,
        downloading: backgroundDownloadControllers.size,
        loading: loading,
        rotationInFlight: rotationInFlight,
        hasLeadership: Boolean(rotationLeadership),
        lastConfig: lastConfig,
      }; },
    };`
  );
  vm.runInNewContext(script, context);
  return {
    api: window.test, media: window.AstrBotPaletteMedia, document, requests, created, revoked, events,
    hide(value) { hidden = value; }, reduce(value) { reduced = value; },
    failVideo() { failNextVideo = true; }, failImage(value) { badNextImage = value; },
    setFetch(fn) { context.fetch = fn; },
    runTimeout(delay) {
      for (const [id, timer] of timeouts) {
        if (timer.delay === delay) { timeouts.delete(id); timer.fn(); }
      }
    },
  };
}

async function testHiddenRefreshLifecycle() {
  // GET/CSS/轮换 POST 迟到都不能在隐藏/离开后重新创建媒体；
  // 恢复可见需要重新读取最新配置，而不是补播旧请求。
  for (const stage of ["config", "css", "rotation-post", "pagehide-css"]) {
    const env = environment();
    await env.api.apply(videoConfig("/old"), "t", false);
    const previous = env.api.state().objectUrl;
    let config = {
      ...videoConfig("/stale"),
      background_rotation_enabled: true,
      landscape_background_image: "stale.mp4",
      landscape_background_images: ["stale.mp4", "next.mp4"],
    };
    let resolveWaiting;
    const waiting = new Promise(resolve => { resolveWaiting = resolve; });
    let markStarted;
    const started = new Promise(resolve => { markStarted = resolve; });
    const downloads = [];
    let postCount = 0;
    let hold = true;
    env.setFetch(async (url, options) => ({
      ok: true, headers: { get: () => "" },
      text: async () => {
        if (hold && (stage === "css" || stage === "pagehide-css")) {
          markStarted(); await waiting;
        }
        return "";
      },
      json: async () => {
        if (options?.method === "POST") {
          postCount++;
          if (hold && stage === "rotation-post") {
            markStarted(); return await waiting;
          }
          return {config};
        }
        if (hold && stage === "config") {
          markStarted(); return await waiting;
        }
        return {...config};
      },
      blob: async () => { downloads.push(url); return new Blob(["media"]); },
    }));
    const isRotation = stage === "rotation-post";
    if (isRotation) env.api.acquireTestLeadership();
    const inFlight = isRotation ? env.api.rotate() : env.api.refresh();
    await started;
    if (stage === "pagehide-css") {
      env.events.pagehide();
    } else {
      env.hide(true);
      env.events.visibilitychange();
    }
    resolveWaiting(isRotation ? {config} : {...config});
    await inFlight;
    await new Promise(setImmediate);
    assert.equal(downloads.length, 0, `${stage} 迟到时不能启动媒体下载`);
    assert.equal(env.api.state().loading, false);
    assert.equal(env.api.state().rotationInFlight, false);
    assert.equal(env.api.state().hasLeadership, false);
    if (stage !== "pagehide-css") {
      assert.equal(env.api.state().objectUrl, previous, "隐藏保留已成功背景");
      // hash/online/resize 在隐藏时也不能开启新媒体任务。
      await env.api.refresh({retryFailedMedia: true});
      await env.api.apply(videoConfig("/hidden-resize"), "t", false);
      assert.equal(downloads.length, 0);
    } else {
      assert.equal(env.api.state().cache, 0, "pagehide 必须整体回收");
    }
    config = videoConfig("/latest");
    hold = false;
    env.hide(false);
    if (stage === "pagehide-css") env.events.pageshow({persisted: true});
    else env.events.visibilitychange();
    await new Promise(resolve => setTimeout(resolve, 130));
    assert.equal(env.api.state().url, "/latest", `${stage} 恢复应读取新配置`);
    assert.equal(env.api.state().loading, false);
    assert(downloads.some(url => url.startsWith("/latest?")));
    assert.equal(postCount, isRotation ? 1 : 0, "恢复不补播轮换");
    env.api.inactive();
  }
}

function videoConfig(url = "/video") {
  return {
    enabled: true, auto_theme_enabled: false,
    dynamic_background_enabled: true, landscape_background_url: url,
    landscape_background_media: { media_type: "video", cover_url: `${url}-cover` },
  };
}

async function testRuntime() {
  let env = environment();
  assert(env.api, "bootstrap 真实函数未导出");
  let config = videoConfig();
  await env.api.apply(config, "secret", false);
  const video = env.created.find((element) => element.tagName === "VIDEO");
  assert(video.muted && video.loop && video.playsInline);
  assert(video.parentNode);
  assert.equal(env.api.state().status, "video_ready");
  assert.equal(env.api.state().inflight, 0);
  assert(env.requests.every((request) => request.options.headers.Authorization === "Bearer secret"));
  assert(!env.requests.some((request) => request.url.includes("secret")));
  const count = env.requests.length;
  await env.api.apply({ ...config, background_dim: 0.8 }, "secret", false);
  assert.equal(env.requests.length, count);
  assert.equal(env.created.filter((element) => element.tagName === "VIDEO").length, 1);
  assert.equal(video.currentTime, 7);
  assert.equal(video.playCount, 1, "普通刷新不能重复申请已播放视频的 play()");
  env.hide(true); env.api.visibility(); assert(video.paused);
  env.hide(false); env.api.visibility(); await Promise.resolve(); assert(!video.paused);
  video.dispatch("error"); assert.equal(video.style.visibility, "hidden"); assert.equal(env.api.state().status, "static_fallback");
  env.api.inactive(); assert(!video.parentNode); assert.equal(video.src, "");
  assert.equal(env.api.state().cache, 0); assert.equal(env.api.state().inuse, 0);

  env = environment();
  await env.api.apply(videoConfig(), "t", false);
  const running = env.created.find((element) => element.tagName === "VIDEO");
  await env.api.apply({ ...videoConfig(), dynamic_background_enabled: false }, "t", false);
  assert(!running.parentNode); assert(running.paused);
  assert.equal(env.api.state().status, "image_ready");
  assert.equal(env.api.state().cache, 1, "旧视频未在解除引用后回收");
  env.reduce(true);
  await env.api.apply(videoConfig(), "t", false);
  assert.equal(env.created.filter((element) => element.tagName === "VIDEO").length, 1);
  env.api.inactive();

  env = environment();
  env.failVideo();
  await env.api.apply(videoConfig(), "t", false);
  assert.equal(env.api.state().status, "static_fallback");
  assert(env.created.filter((element) => element.tagName === "VIDEO").every((element) => !element.parentNode));
  const old = env.api.state().objectUrl;
  env.failVideo();
  await assert.rejects(env.api.apply(videoConfig("/bad"), "t", false), /保留原背景/);
  assert.equal(env.api.state().objectUrl, old);
  assert.equal(env.api.state().inflight, 0);
  env.failImage(true);
  await assert.rejects(env.api.apply({ ...videoConfig("/bad-image"), landscape_background_media: { media_type: "image" } }, "t", false));
  assert.equal(env.api.state().objectUrl, old);
  env.api.inactive();

  env = environment();
  const first = new Element("video"); first.readyState = 0;
  const ready = env.media.waitForFirstFrame(first, 50);
  first.dispatch("loadeddata"); await ready;
  assert.equal(first.listeners.loadeddata.size, 0);
  const invalid = new Element("video"); invalid.readyState = 0;
  const rejected = env.media.waitForFirstFrame(invalid, 50);
  invalid.dispatch("error"); await assert.rejects(rejected);
  const timeout = new Element("video"); timeout.readyState = 0;
  await assert.rejects(env.media.waitForFirstFrame(timeout, 5), /超时/);
  const cancelled = new Element("video"); cancelled.readyState = 0;
  const preparation = new AbortController();
  const waiting = env.media.waitForFirstFrame(cancelled, 10000, preparation.signal);
  preparation.abort();
  await assert.rejects(waiting, (error) => error.name === "AbortError");
  assert.equal(cancelled.listeners.loadeddata.size, 0);
  assert.equal(cancelled.listeners.error.size, 0);
  assert.equal(env.media.videoObjectFit("stretch"), "fill");
  assert.equal(env.media.videoObjectFit("auto"), "none");

  // 下载晚到、取消与缓存代数：回收后不得回填缓存。
  env = environment();
  let resolveBlob;
  env.setFetch(async () => ({ ok: true, headers: { get: () => "" }, blob: () => new Promise((resolve) => { resolveBlob = resolve; }) }));
  const pending = env.api.fetchBackground("/late", "t");
  await new Promise(setImmediate);
  env.api.revoke();
  resolveBlob(new Blob(["late"]));
  await assert.rejects(pending, /作废|取消/);
  assert.equal(env.api.state().cache, 0);

  // 同 URL 并发完成，只有一个对象 URL；消费者各自解除保护。
  env = environment();
  const urls = await Promise.all([env.api.fetchBackground("/same", "t"), env.api.fetchBackground("/same", "t")]);
  assert.equal(urls[0], urls[1]);
  env.api.release(urls[0]); env.api.release(urls[1]);
  assert.equal(env.api.state().inflight, 0);
  env.api.revoke();
  assert.equal(env.revoked.length, 1);

  env = environment();
  await env.api.apply(videoConfig("/first"), "t", false);
  const fadingVideo = env.created.find((element) => element.tagName === "VIDEO");
  await env.api.apply(videoConfig("/second"), "t", true);
  assert(fadingVideo.parentNode, "叠化结束前旧视频需保留图层引用");
  assert.equal(env.api.state().url, "/second");
  await new Promise((resolve) => setTimeout(resolve, 800));
  assert(!fadingVideo.parentNode, "叠化结束后必须释放旧视频");
  assert.equal(env.api.state().inflight, 0);
  env.api.inactive();
  assert.equal(env.api.state().inuse, 0);
}

async function testPlaybackRecovery() {
  // 暂停打断尚未完成的恢复播放：旧回调不得污染新申请。
  let env = environment();
  await env.api.apply(videoConfig(), "t", false);
  const video = env.created.find((element) => element.tagName === "VIDEO");
  const normalPlay = video.play.bind(video);
  const normalPause = video.pause.bind(video);
  let rejectPending;
  video.play = function () {
    this.paused = false;
    return new Promise((resolve, reject) => { rejectPending = reject; });
  };
  video.pause = function () {
    normalPause();
    if (rejectPending) {
      rejectPending(new DOMException("interrupted by pause", "AbortError"));
      rejectPending = null;
    }
  };
  env.hide(true); env.api.visibility();
  env.hide(false); env.api.visibility();
  env.hide(true); env.api.visibility();
  video.play = normalPlay;
  env.hide(false); env.api.visibility();
  await new Promise(setImmediate);
  assert(!video.paused);
  assert.equal(env.api.state().status, "video_ready");
  assert.notEqual(video.style.visibility, "hidden");
  env.api.inactive();

  // 首次失败不在普通路由刷新中循环下载，明确恢复时机允许一次重试。
  env = environment();
  env.failVideo();
  await env.api.apply(videoConfig(), "t", false);
  const afterFailure = env.requests.length;
  await env.api.apply(videoConfig(), "t", false);
  assert.equal(env.requests.length, afterFailure);
  await env.api.apply(videoConfig(), "t", false, true);
  assert.equal(env.api.state().status, "video_ready");
  assert.equal(env.created.filter((element) => element.tagName === "VIDEO").length, 2);
  const restored = env.created.find((element) => element.tagName === "VIDEO" && element.parentNode);
  const requests = env.requests.length;
  restored.dispatch("error");
  await env.api.apply(videoConfig(), "t", false, true);
  await new Promise(setImmediate);
  assert.equal(env.api.state().status, "video_ready");
  assert.equal(env.requests.length, requests, "已保留的视频重试应复用 URL");
  assert.equal(restored.currentTime, 7);
  env.api.inactive();
}

async function testSlowDownloadInvalidation() {
  const env = environment();
  await env.api.apply(videoConfig("/old"), "t", false);
  let config = videoConfig("/slow");
  let slowSignal;
  let configurationGets = 0;
  let startSlowDownload;
  const started = new Promise((resolve) => { startSlowDownload = resolve; });
  env.setFetch(async (url, options) => {
    if (url.startsWith("/slow?")) {
      slowSignal = options.signal;
      return {
        ok: true, headers: { get: () => "" },
        blob: () => new Promise((resolve, reject) => {
          slowSignal.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
          startSlowDownload();
        }),
      };
    }
    return {
      ok: true, headers: { get: () => "" }, text: async () => "",
      json: async () => { configurationGets++; return { ...config }; },
      blob: async () => new Blob(["cover"]),
    };
  });
  const preparing = env.api.refresh();
  await started;
  config = { ...config, enabled: false };
  await env.api.refresh({ invalidateMedia: true, retryFailedMedia: true });
  assert(slowSignal.aborted, "配置失效必须立即取消旧下载");
  await preparing;
  await new Promise((resolve) => setTimeout(resolve, 130));
  assert.equal(env.api.state().loading, false);
  assert.equal(env.api.state().lastConfig, null);
  assert(configurationGets >= 2, "取消后应读取最新配置");
  assert(!env.created.some((element) => element.tagName === "VIDEO" && element.parentNode));
  assert.equal(env.api.state().cache, 0);
  assert.equal(env.api.state().downloading, 0);
  env.api.inactive();

  // 网络停滞时必须释放下载控制器，不等待浏览器自行超时。
  const timeoutEnv = environment();
  let timeoutSignal;
  timeoutEnv.setFetch(async (url, options) => {
    timeoutSignal = options.signal;
    return {
      ok: true, headers: { get: () => "" },
      blob: () => new Promise((resolve, reject) => {
        timeoutSignal.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
      }),
    };
  });
  const timedOut = timeoutEnv.api.fetchBackground("/timeout", "t", "video/*");
  await new Promise(setImmediate);
  timeoutEnv.runTimeout(60000);
  await assert.rejects(timedOut, /下载超时/);
  assert(timeoutSignal.aborted);
  assert.equal(timeoutEnv.api.state().downloading, 0);
  assert.equal(timeoutEnv.api.state().cache, 0);
}

async function testImport() {
  const root = process.argv[3];
  const importer = await import(pathToFileURL(`${root}/pages/settings/wallpaper-import.js`));
  const media = await import(pathToFileURL(`${root}/pages/settings/media.js`));
  const file = (path, content) => ({ path, file: new File([content], path.split("/").at(-1)) });
  const project = (path, data) => file(`${path}/project.json`, JSON.stringify(data));
  const entries = [
    project("video", { type: "video", title: "<b>Video</b>", file: "wall.mp4", preview: "preview.jpg" }),
    file("video/wall.mp4", "video"), file("video/preview.jpg", "preview"),
    project("scene", { type: "scene", file: "scene.pkg", preview: "preview.jpg" }),
    file("scene/scene.pkg", "pkg"), file("scene/preview.jpg", "preview"), file("scene/texture.png", "texture"),
    project("web", { type: "web", file: "index.html" }), file("web/index.html", "html"),
    project("application", { type: "application", file: "app.exe" }), file("application/app.exe", "exe"),
    project("static", { file: "original.png", preview: "preview.jpg" }), file("static/original.png", "image"), file("static/preview.jpg", "preview"),
    project("missing", { type: "video", file: "missing.mp4" }),
    project("escape", { file: "../outside.png" }), file("outside.png", "image"),
    file("broken/project.json", "broken"), file("broken/preview.jpg", "preview"),
    file("plain/photo.jpeg", "image"),
    file("unknown/scene.pkg", "pkg"), file("unknown/texture.png", "texture"),
    project("ambiguous", { file: "texture.png" }),
    file("ambiguous/scene.pkg", "pkg"), file("ambiguous/texture.png", "texture"),
  ];
  const result = await importer.scanWallpaperFiles(entries);
  assert.equal(result.items.length, 4);
  assert.equal(result.skipped.unsupported, 3);
  assert.equal(result.skipped.invalid, 3);
  assert(!result.items.some((item) => /preview|texture/.test(item.id)));
  assert.equal(result.items[0].file.name, "wall.mp4");
  assert.equal(result.items[0].name, "<b>Video</b>");
  for (const path of ["../x.png", "C:\\x.png", "/tmp/x.png", "https://x/a.png"]) assert.equal(importer.projectPath("p", path), "");
  assert.equal(importer.projectPath("p", "assets\\wall.png"), "p/assets/wall.png");
  const cancellation = await importer.pickWallpaperDirectory({
    showDirectoryPicker: async () => { throw new DOMException("cancelled", "AbortError"); },
  });
  assert.equal(cancellation, null);
  await assert.rejects(importer.pickWallpaperDirectory({
    showDirectoryPicker: async () => { throw new DOMException("iframe blocked", "SecurityError"); },
  }), /iframe blocked/);
  const entriesFromHandle = await importer.pickWallpaperDirectory({
    showDirectoryPicker: async (options) => {
      assert.equal(options.mode, "read");
      return { async *entries() {
        yield ["wallpaper.png", { kind: "file", getFile: async () => entries.at(-1).file }];
      } };
    },
  });
  assert.equal(entriesFromHandle.length, 1);
  let uploads = 0;
  assert(await importer.importWallpaperItem(result.items[0], "portrait", async (selected) => { uploads++; assert.equal(selected.name, "wall.mp4"); }));
  assert.equal(result.items[0].state, "imported");
  await importer.importWallpaperItem(result.items[0], "portrait", async () => { uploads++; });
  assert.equal(uploads, 1);
  assert.equal(await importer.importWallpaperItem(result.items[1], "landscape", async () => { throw new Error("failed"); }), false);
  assert.equal(result.items[0].state, "imported"); assert.equal(result.items[1].state, "failed");
  assert(await importer.importWallpaperItem(result.items[1], "landscape", async () => {}));
  const session = importer.createWallpaperImportSession();
  session.remember(result.items[0]);
  const rescan = await importer.scanWallpaperFiles(entries);
  session.restore(rescan.items);
  assert.equal(rescan.items[0].state, "imported", "重选同一目录须保留成功标记");
  await importer.importWallpaperItem(rescan.items[0], "portrait", async () => { uploads++; });
  assert.equal(uploads, 1);
  const changedSize = { ...rescan.items[0], state: "ready", file: new File(["changed video"], "wall.mp4", { lastModified: rescan.items[0].file.lastModified }) };
  const changedTime = { ...rescan.items[0], state: "ready", file: new File(["video"], "wall.mp4", { lastModified: rescan.items[0].file.lastModified + 1 }) };
  const otherDirectory = { ...rescan.items[0], state: "ready", id: "other/video/wall.mp4" };
  session.restore([changedSize, changedTime, otherDirectory]);
  assert([changedSize, changedTime, otherDirectory].every((item) => item.state === "ready"));
  const realWebp = new File([fs.readFileSync(`${root}/tests/fixtures/valid-webp-multibyte-length.webp`)], "misnamed.jpg", { type: "" });
  assert.equal((await media.inspectFile(realWebp)).mime, "image/webp");
  const png = new File([fs.readFileSync(`${root}/tests/fixtures/sample.mp4`)], "wrong-name.png", { type: "" });
  assert.equal((await media.inspectFile(png)).kind, "video");
  const bundle = media.bundleFile(png, new Blob(["cover"]));
  const bytes = new Uint8Array(await bundle.arrayBuffer());
  const headerSize = new TextEncoder().encode(media.BUNDLE_MAGIC).length;
  assert.equal(new TextDecoder().decode(bytes.slice(0, headerSize)), media.BUNDLE_MAGIC);
  assert.equal(new DataView(bytes.buffer).getUint32(headerSize), 5);
  await assert.rejects(media.inspectFile(new File(["bad"], "fake.mp4")), /无法识别/);
  const huge = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "large.png");
  const head = new Uint8Array([137,80,78,71,13,10,26,10]);
  await assert.rejects(media.inspectFile(new File([head, huge], "large.png")), /10MiB/);
}

async function testPreviewBridge() {
  const { attachPreviewBridge, isPaletteSettingsMessage } = require("../palette/media_runtime.js");
  const callbacks = {};
  const responses = [];
  const source = { postMessage(data) { responses.push(data); } };
  let path = "/api/plugin/page/content/astrbot_plugin_palette/settings/";
  const root = {
    URL, AbortController, location: { origin: "https://test.example", href: "https://test.example/" },
    document: { querySelectorAll() { return [{ contentWindow: source, getAttribute() { return path; } }]; } },
    addEventListener(kind, fn) { callbacks[kind] = fn; },
    removeEventListener(kind) { delete callbacks[kind]; },
    setTimeout, clearTimeout,
    fetch: async (url, options) => {
      assert.equal(options.headers.Authorization, "Bearer parent-secret");
      assert.equal(url, "/api/v1/plugins/extensions/astrbot_plugin_palette/backgrounds/sample.mp4");
      return { ok: true, headers: { get: (key) => key === "Content-Type" ? "video/mp4" : "4" }, arrayBuffer: async () => new ArrayBuffer(4) };
    },
  };
  const event = { source, origin: "null", data: { type: "astrbot-palette:media-request", filename: "sample.mp4", requestId: "test" } };
  assert(isPaletteSettingsMessage(event, root));
  assert(!isPaletteSettingsMessage({ ...event, source: {} }, root));
  assert(!isPaletteSettingsMessage({ ...event, origin: "https://attacker.example" }, root));
  const bridge = attachPreviewBridge(root, () => "parent-secret");
  await callbacks.message(event);
  assert.equal(responses.length, 1);
  assert.equal(responses[0].contentType, "video/mp4");
  assert.equal(responses[0].buffer.byteLength, 4);
  assert(!JSON.stringify(responses).includes("parent-secret"));
  await callbacks.message({ ...event, data: { ...event.data, filename: "../secret.mp4" } });
  assert.equal(responses.length, 1);
  path = "/api/plugin/page/content/other-plugin/settings/";
  assert(!isPaletteSettingsMessage(event, root));
  await callbacks.message(event);
  assert.equal(responses.length, 1);
  bridge.destroy();
  assert(!callbacks.message);
}

(async () => {
  await testRuntime();
  await testPlaybackRecovery();
  await testSlowDownloadInvalidation();
  await testHiddenRefreshLifecycle();
  await testImport();
  await testPreviewBridge();
  console.log("媒体运行时、上传包与 Wallpaper Engine 目录行为验证通过");
})().catch((error) => { console.error(error); process.exitCode = 1; });
