/* 本机缓存真实浏览器回归；使用独立临时浏览器目录，不访问用户配置或真实 AstrBot。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const [root, bootstrapPath, playwrightPath, chromiumPath] = process.argv.slice(2);
const { chromium } = require(playwrightPath);
const tempRoot = fs.realpathSync(os.tmpdir());
const profile = fs.mkdtempSync(path.join(tempRoot, "palette052-cache-"));
const prefix = "/api/v1/plugins/extensions/astrbot_plugin_palette/";
const videoUrl = prefix + "backgrounds/existing.mp4";
const coverUrl = prefix + "background-cover?filename=existing.mp4";
const item = { filename: "existing.mp4", url: videoUrl, cover_url: coverUrl, media_type: "video" };
let config = {
  enabled: true, auto_theme_enabled: false, dynamic_background_enabled: true,
  landscape_background_image: "existing.mp4", landscape_background_images: ["existing.mp4"],
  landscape_background_items: [item], portrait_background_items: [], background_items: [],
  landscape_background_url: videoUrl,
  landscape_background_media: { media_type: "video", cover_url: coverUrl },
};
const counts = { video: 0, cover: 0, config: 0 };
let denied = false;
const bootstrap = fs.readFileSync(bootstrapPath, "utf8").replace(
  "    setupPaletteSync();\n    bootstrapRecommendedDarkTheme();\n    refreshPalette({ allowInitialRandom: true });",
  `window.cacheTest = {cache:persistentMediaCache, refresh:refreshPalette, inactive:setInactive,
    state:function(){return {url:currentBackgroundUrl,loading:loading};}};
    localStorage.setItem("token", "local-cache-test");
    refreshPalette();`,
);
function settingsBridge() {
  return `<script>
    window.AstrBotPluginPage = {
      ready:async()=>({isDark:true}),onContext(){},
      apiGet:async(endpoint,params)=>{
        if(endpoint==="status")return {plugin:{version:"0.5.3"},injection:{}};
        if(endpoint==="background-thumbnail")return {data_url:""};
        return await (await fetch("${prefix}config",{headers:{Authorization:"Bearer local-cache-test"}})).json();
      }
    };
  </script>`;
}
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  const pathname = url.pathname;
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin":"*", "Access-Control-Allow-Headers":"Authorization",
      "Access-Control-Allow-Methods":"GET",
    });
    res.end(); return;
  }
  if (pathname === "/runtime") {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end('<html><body><div id="app"></div><script src="/bootstrap.js"></script></body></html>');
    return;
  }
  if (pathname === "/bootstrap.js") {
    res.writeHead(200, { "Content-Type": "text/javascript" }); res.end(bootstrap); return;
  }
  if (pathname === prefix + "config") {
    counts.config++;
    if (denied || req.headers.authorization !== "Bearer local-cache-test") {
      res.writeHead(401); res.end(); return;
    }
    res.writeHead(200, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
    res.end(JSON.stringify(config)); return;
  }
  if (pathname === "/theme.css") {
    res.writeHead(200, { "Content-Type": "text/css" }); res.end(""); return;
  }
  if (pathname === videoUrl || pathname === prefix + "background-cover") {
    const kind = pathname === videoUrl ? "video" : "cover";
    counts[kind]++;
    const file = kind === "video" ? "sample.mp4" : "valid-webp-multibyte-length.webp";
    const bytes = fs.readFileSync(path.join(root, "tests/fixtures", file));
    res.writeHead(200, { "Content-Type": kind === "video" ? "video/mp4" : "image/webp", "Content-Length": bytes.length });
    res.end(bytes); return;
  }
  const settingsPrefix = "/api/plugin/page/content/astrbot_plugin_palette/settings/";
  if (pathname.startsWith(settingsPrefix)) {
    const name = pathname.slice(settingsPrefix.length) || "index.html";
    if (!/^[a-z.-]+$/.test(name)) { res.writeHead(404); res.end(); return; }
    const file = path.join(root, "pages/settings", name);
    let bytes = fs.readFileSync(file);
    if (name === "index.html") bytes = Buffer.from(bytes.toString().replace("<head>", "<head>" + settingsBridge()));
    res.writeHead(200, {
      "Content-Type": {".html":"text/html",".js":"text/javascript",".css":"text/css"}[path.extname(name)],
      "Access-Control-Allow-Origin": "*",
    });
    res.end(bytes); return;
  }
  res.writeHead(404); res.end();
});

async function ready(page) {
  await page.goto(origin + "/runtime");
  await page.waitForFunction(() => window.cacheTest && !window.cacheTest.state().loading &&
    document.querySelector("video") && !document.querySelector("video").paused);
  return page.evaluate(() => window.cacheTest.cache.stats());
}
let origin;
let context;
let assertions = 0;
function check(value, message) { assert(value, message); assertions++; }
(async () => {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  try {
    context = await chromium.launchPersistentContext(profile, { headless:true, executablePath:chromiumPath });
    let page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const first = await ready(page);
    check(first.count === 2, "已设置的旧壁纸和封面首次打开应自动入库");
    check(counts.video === 1 && counts.cover === 1, "首次只下载一次");
    const initialCounts = {...counts};
    await ready(page);
    check(counts.video === initialCounts.video && counts.cover === initialCounts.cover, "刷新不再下载媒体");
    check(counts.config > initialCounts.config, "缓存命中仍核验最新登录配置");
    await context.close(); context = null;
    // 使用同一个独立磁盘目录重启真实 Chromium，而不是只保留内存对象。
    context = await chromium.launchPersistentContext(profile, { headless:true, executablePath:chromiumPath });
    page = await context.newPage();
    page.on("pageerror", error => errors.push(error.message));
    await ready(page);
    check(counts.video === initialCounts.video && counts.cover === initialCounts.cover, "浏览器重启后磁盘缓存可复用");

    // 实际 opaque iframe、原设置页、来源校验消息通道和清理按钮。
    await page.evaluate(() => {
      const frame = document.createElement("iframe");
      frame.src = "/api/plugin/page/content/astrbot_plugin_palette/settings/";
      frame.setAttribute("sandbox", "allow-scripts allow-forms allow-downloads");
      frame.style.width = "390px"; frame.style.height = "840px"; frame.id = "settings";
      document.body.append(frame);
    });
    const frame = await page.waitForEvent("framenavigated", {
      predicate: frame => frame.url().includes("/api/plugin/page/content/"), timeout:1000,
    }).catch(() => page.frames().find(frame => frame.url().includes("/api/plugin/page/content/")));
    await frame.waitForFunction(() => document.querySelector("#local-cache-status")?.textContent.includes("普通缓存"));
    check(await frame.evaluate(() => {
      try { localStorage.getItem("token"); return false; } catch (_) { return true; }
    }), "在真实 opaque 沙箱中操作缓存");
    await frame.locator(".gallery-preview").click();
    await frame.waitForFunction(() => document.querySelector("#media-preview-dialog video")?.paused === false);
    check(counts.video === initialCounts.video, "独立预览也复用已缓存视频");
    await frame.locator("[data-close-preview]").click();
    await frame.locator("#clear-local-cache").click();
    await frame.waitForFunction(() => document.querySelector("#status-text").textContent.includes("已清理本机缓存"));
    check((await page.evaluate(() => window.cacheTest.cache.stats())).count === 0, "真实清理按钮清空磁盘缓存");
    check(await page.evaluate(() => !document.querySelector("video").paused), "清理不影响当前播放");
    await ready(page);
    check(counts.video === initialCounts.video + 1, "清理后首次重新下载");
    check(await page.evaluate(() => {
      const storage = localStorage;
      return storage.getItem("token") === "local-cache-test";
    }), "清理不删除登录状态");

    // 验证普通 LRU 与大素材例外，用小预算执行相同算法，避免写入真实 GB 数据。
    const policy = await page.evaluate(async () => {
      const cache = AstrBotPaletteCache.create(window, {databaseName:"cache-policy-test",maxBytes:12});
      const other = AstrBotPaletteCache.create(window, {databaseName:"cache-policy-test",maxBytes:12});
      const info = {background_items:["a","b","c","large1","large2"].map(url => ({url}))};
      await cache.setConfig(info); await other.setConfig(info);
      const put = async (url,size) => {
        const entry = await cache.read(url);
        return cache.write(url,new Blob([new Uint8Array(size)]),entry.epoch);
      };
      await put("a",6); await put("b",6);
      await cache.read("a");
      await put("c",6);
      const lru = !(await cache.read("b")).blob && Boolean((await cache.read("a")).blob);
      await put("large1",13); await put("large2",20);
      const stats = await cache.stats();
      const ticket = await cache.read("c");
      await other.clear();
      const preventedRefill = !(await cache.write("c",new Blob(["c"]),ticket.epoch));
      const abort = new AbortController(); abort.abort();
      const cancelled = !(await cache.read("a",abort.signal)).blob;
      await put("a",6);
      await cache.setConfig({background_items:[]});
      const pruned = (await cache.stats()).count===0;
      cache.close();other.close();
      return {lru,stats,preventedRefill,cancelled,pruned};
    });
    check(policy.lru, "淘汰最久未使用的普通素材");
    check(policy.stats.budgetBytes === 12 && policy.stats.largeBytes === 33 &&
      policy.stats.largeCount === 2 && policy.stats.bytes === 45, "全部大素材保存且不占普通预算");
    check(policy.preventedRefill, "跨标签页清理后旧下载不回填");
    check(policy.cancelled && policy.pruned, "取消与删除引用清理生效");

    // 缓存存在也不能在登录配置失败时显示；恢复后继续复用。
    denied = true;
    await page.reload();
    await page.waitForFunction(() => window.cacheTest && !window.cacheTest.state().loading);
    check(await page.evaluate(() => !document.querySelector("video")), "登录校验失败不复用缓存");
    denied = false;
    await ready(page);

    // 浏览器拒绝 IDB 时正常下载播放，读取/写入失败也无需用户操作。
    const fallback = await context.newPage();
    await fallback.addInitScript(() => Object.defineProperty(window,"indexedDB",{get(){throw new DOMException("blocked","SecurityError");}}));
    const previousDownloads = counts.video;
    const fallbackStats = await ready(fallback);
    check(!fallbackStats.available && counts.video === previousDownloads + 1, "存储不可用时回退网络");
    await fallback.close();
    // 主动中止真实 IDB 写入事务，核对存储失败后的联网播放与事务回滚。
    await page.evaluate(() => window.cacheTest.cache.clear());
    const failedWritePage = await context.newPage();
    failedWritePage.on("pageerror", error => errors.push(error.message));
    await failedWritePage.addInitScript(() => {
      const put = IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put = function (...args) {
        const request = put.apply(this,args);
        if (this.name === "blobs") queueMicrotask(() => {
          try { this.transaction.abort(); } catch (_) {}
        });
        return request;
      };
    });
    const beforeWriteFailure = counts.video;
    const failedWriteStats = await ready(failedWritePage);
    check(failedWriteStats.count === 0 && counts.video === beforeWriteFailure + 1,
      "真实 IDB 写入失败回退联网播放且不留下半份缓存");
    await failedWritePage.close();
    check(errors.length===0, "无页面脚本错误");
    console.log(JSON.stringify({result:"pass",assertions,counts,policy,errors}));
  } finally {
    if (context) await context.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    if (path.dirname(fs.realpathSync(profile)) !== tempRoot || !path.basename(profile).startsWith("palette052-cache-")) {
      throw new Error("临时浏览器目录范围核验失败");
    }
    fs.rmSync(profile,{recursive:true,force:true});
  }
})().catch(error => { console.error(error);process.exitCode=1; });
