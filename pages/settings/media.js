// 素材上传和独立预览共用：真实类型探测、静态封面、单文件上传包。
export const BUNDLE_MAGIC = "PALETTE-MEDIA-1\n";

export async function inspectFile(file) {
  const head = new Uint8Array(await file.slice(0, 4096).arrayBuffer());
  const starts = (bytes, offset = 0) => bytes.every((byte, i) => head[i + offset] === byte);
  let kind = "";
  let mime = "";
  if (starts([255, 216, 255])) { kind = "image"; mime = "image/jpeg"; }
  else if (starts([137, 80, 78, 71, 13, 10, 26, 10])) { kind = "image"; mime = "image/png"; }
  else if (starts([71, 73, 70, 56, 55, 97]) || starts([71, 73, 70, 56, 57, 97])) { kind = "image"; mime = "image/gif"; }
  else if (starts([82, 73, 70, 70]) && starts([87, 69, 66, 80], 8)) { kind = "image"; mime = "image/webp"; }
  else if (head.length >= 16 && starts([102, 116, 121, 112], 4)) { kind = "video"; mime = "video/mp4"; }
  else if (starts([26, 69, 223, 163])) { kind = "video"; mime = "video/webm"; }
  else {
    // 只对文本 SVG 使用 UTF-8；二进制头的字节偏移不能按字符计算。
    const text = new TextDecoder().decode(head);
    if (/^\s*(?:<\?xml|<!--|<svg)/.test(text.replace(/^\uFEFF/, "")) && text.includes("<svg")) {
      kind = "svg"; mime = "image/svg+xml";
    }
  }
  if (!kind) throw new Error(`不支持或无法识别的素材：${file.name}`);
  return { kind, mime };
}

export function safeSvgText(text) {
  if (/<!DOCTYPE|<!ENTITY|<\?xml-stylesheet/i.test(text)) throw new Error("SVG 不允许文档实体或外部样式");
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  if (doc.querySelector("parsererror") || doc.documentElement.localName !== "svg") throw new Error("SVG 文件已损坏");
  const checkCss = (css) => {
    if (/\\|\/\*|@import|expression\s*\(|javascript\s*:|behavior\s*:|-moz-binding/i.test(css)) throw new Error("SVG 包含不支持或不安全的样式");
    for (const match of css.matchAll(/url\(\s*(['"]?)(.*?)\1\s*\)/gi)) {
      if (!match[2].trim().startsWith("#")) throw new Error("SVG 不允许外部资源");
    }
  };
  for (const element of doc.querySelectorAll("*")) {
    if (element.namespaceURI !== "http://www.w3.org/2000/svg" && element.namespaceURI !== null) throw new Error("SVG 包含非 SVG 内容");
    if (/^(script|foreignobject|a|audio|video|iframe|object|embed|link|base|meta|handler|listener)$/i.test(element.localName)) throw new Error("SVG 包含不可用元素");
    for (const attribute of element.attributes) {
      const name = attribute.localName.toLowerCase();
      if (name.startsWith("on")) throw new Error("SVG 不允许事件属性");
      if (name === "base" && attribute.value.trim()) throw new Error("SVG 不允许外部基础路径");
      if (["href", "src"].includes(name) && attribute.value && !attribute.value.startsWith("#") && !/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(attribute.value)) throw new Error("SVG 不允许外部引用");
      if (/^(animate|set|animatetransform)$/i.test(element.localName) && name === "attributename" && /^(?:.*:)?(?:href|src|style|on.*)$/i.test(attribute.value)) throw new Error("SVG 动画不能修改资源或事件");
      checkCss(attribute.value);
    }
    if (element.localName === "style") checkCss(element.textContent || "");
  }
  // 缺少尺寸的 SVG 使用 viewBox 比例；不改变原素材，只用于封面生成。
  const root = doc.documentElement;
  if (!root.getAttribute("width") || !root.getAttribute("height")) {
    const box = (root.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
    root.setAttribute("width", String(box.length === 4 && box[2] > 0 ? box[2] : 300));
    root.setAttribute("height", String(box.length === 4 && box[3] > 0 ? box[3] : 150));
  }
  return new XMLSerializer().serializeToString(doc);
}

function waitEvent(element, name, timeout = 15000, signal) {
  return new Promise((resolve, reject) => {
    const finish = (error) => {
      clearTimeout(timer);
      element.removeEventListener(name, ready);
      element.removeEventListener("error", failed);
      signal?.removeEventListener("abort", cancelled);
      error ? reject(error) : resolve();
    };
    const ready = () => finish();
    const failed = () => finish(new Error("浏览器无法解码此素材，请检查文件或视频编码"));
    const cancelled = () => finish(new DOMException("预览已关闭", "AbortError"));
    const timer = setTimeout(() => finish(new Error("素材读取超时，请重试或更换浏览器")), timeout);
    element.addEventListener(name, ready, { once: true });
    element.addEventListener("error", failed, { once: true });
    if (signal?.aborted) cancelled();
    else signal?.addEventListener("abort", cancelled, { once: true });
  });
}

export async function makeCover(file, info, doc = document) {
  const source = info.kind === "svg"
    ? new Blob([safeSvgText(await file.text())], { type: info.mime })
    : new Blob([file], { type: info.mime });
  const url = URL.createObjectURL(source);
  const media = info.kind === "video" ? doc.createElement("video") : new Image();
  try {
    if (info.kind === "video") {
      media.muted = true;
      media.playsInline = true;
      media.preload = "auto";
    }
    const loaded = waitEvent(media, info.kind === "video" ? "loadeddata" : "load");
    media.src = url;
    if (info.kind === "video") media.load();
    await loaded;
    if (info.kind === "video" && Number.isFinite(media.duration) && media.duration > 0.2) {
      const sought = waitEvent(media, "seeked");
      media.currentTime = Math.min(1, media.duration / 10);
      await sought;
    }
    const width = media.videoWidth || media.naturalWidth;
    const height = media.videoHeight || media.naturalHeight;
    if (!width || !height) throw new Error("素材没有有效画面，无法生成封面");
    const scale = Math.min(1, 1280 / Math.max(width, height));
    const canvas = doc.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    canvas.getContext("2d").drawImage(media, 0, 0, canvas.width, canvas.height);
    const cover = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!cover || cover.size > 4 * 1024 * 1024) throw new Error("封面生成失败或超过 4MiB");
    return cover;
  } finally {
    if (info.kind === "video") {
      media.pause();
      media.removeAttribute("src");
      media.load();
    } else {
      media.src = "";
    }
    URL.revokeObjectURL(url);
  }
}

export function bundleFile(file, cover) {
  const length = new Uint8Array(4);
  new DataView(length.buffer).setUint32(0, cover.size);
  return new File([BUNDLE_MAGIC, length, cover, file], file.name, { type: "application/octet-stream" });
}

export async function prepareUpload(file) {
  const info = await inspectFile(file);
  if (["video", "svg"].includes(info.kind)) return bundleFile(file, await makeCover(file, info));
  return file;
}

export async function fetchMediaBlob(url, signal) {
  // AstrBot 设置页 sandbox 没有 allow-same-origin，不能读取 localStorage。
  // 主页面注入脚本代为鉴权下载，只返回限定素材字节，不下发令牌。
  if (window.parent !== window) {
    const mediaUrl = new URL(url, window.location.href);
    const prefix = "/api/v1/plugins/extensions/astrbot_plugin_palette/";
    const cover = mediaUrl.pathname === prefix + "background-cover";
    const filename = cover ? mediaUrl.searchParams.get("filename") :
      mediaUrl.pathname.startsWith(prefix + "backgrounds/")
        ? decodeURIComponent(mediaUrl.pathname.slice((prefix + "backgrounds/").length)) : "";
    if (mediaUrl.origin !== window.location.origin || !filename) throw new Error("预览素材地址不正确");
    const requestId = `palette-preview-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const response = await new Promise((resolve, reject) => {
      const finish = (error, value) => {
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        signal?.removeEventListener("abort", abort);
        error ? reject(error) : resolve(value);
      };
      const abort = () => {
        window.parent.postMessage({ type: "astrbot-palette:media-cancel", requestId }, mediaUrl.origin);
        finish(new DOMException("预览已关闭", "AbortError"));
      };
      const onMessage = (event) => {
        const data = event.data;
        if (event.source !== window.parent || event.origin !== mediaUrl.origin ||
            data?.type !== "astrbot-palette:media-response" || data.requestId !== requestId) return;
        if (!data.success) finish(new Error(data.message || "素材读取失败"));
        else if (!(data.buffer instanceof ArrayBuffer)) finish(new Error("素材预览响应不正确"));
        else finish(null, data);
      };
      const timer = setTimeout(() => {
        window.parent.postMessage({ type: "astrbot-palette:media-cancel", requestId }, mediaUrl.origin);
        finish(new Error("主页面未响应素材预览，请刷新 AstrBot WebUI 后重试"));
      }, 65000);
      window.addEventListener("message", onMessage);
      if (signal?.aborted) { abort(); return; }
      signal?.addEventListener("abort", abort, { once: true });
      window.parent.postMessage({ type: "astrbot-palette:media-request", requestId, filename, cover }, mediaUrl.origin);
    });
    return new Blob([response.buffer], { type: response.contentType });
  }
  // 独立打开设置页的同源环境仍可直接鉴权获取。
  let token = "";
  try { token = window.localStorage.getItem("token") || ""; } catch (_) {}
  const response = await fetch(url, {
    signal, credentials: "same-origin",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error(`素材读取失败（HTTP ${response.status}）`);
  const blob = await response.blob();
  return blob;
}

export function initMediaPreview(dialog, getConfig, report) {
  let generation = 0;
  let controller = null;
  let objectUrl = "";
  let media = null;
  let mediaErrorListener = null;
  const stage = dialog.querySelector(".media-preview-stage");
  const close = () => {
    generation += 1;
    controller?.abort();
    controller = null;
    if (media && mediaErrorListener) media.removeEventListener("error", mediaErrorListener);
    mediaErrorListener = null;
    if (media?.tagName === "VIDEO") { media.pause(); media.removeAttribute("src"); media.load(); }
    stage.replaceChildren();
    media = null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = "";
    if (dialog.open) dialog.close();
  };
  const update = () => {
    const config = getConfig();
    stage.style.setProperty("--preview-filter", config.filter || "none");
    stage.style.setProperty("--preview-dim", String(config.background_dim ?? 0.5));
    if (media) {
      media.style.objectFit = config.background_fit === "stretch" ? "fill" : config.background_fit === "auto" ? "none" : config.background_fit || "cover";
      media.style.objectPosition = config.background_position || "center center";
    }
  };
  dialog.querySelector("[data-close-preview]").addEventListener("click", close);
  dialog.addEventListener("cancel", close);
  // close 事件异步到达；旧弹窗的事件不得关闭刚重新打开的新预览。
  dialog.addEventListener("close", () => { if (!dialog.open) close(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) close(); });
  window.addEventListener("pagehide", close);
  window.matchMedia?.("(prefers-reduced-motion: reduce)").addEventListener?.("change", close);
  return {
    close, update,
    async open(item) {
      close();
      const request = generation;
      controller = new AbortController();
      dialog.querySelector(".media-preview-title").textContent = item.filename;
      dialog.showModal();
      report("正在准备素材预览");
      try {
        const config = getConfig();
        const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        const frozen = config.dynamic_background_enabled === false || reduced;
        const url = frozen && item.media_type !== "image" ? item.cover_url : item.url;
        if (!url) throw new Error("该素材缺少静态封面");
        const blob = await fetchMediaBlob(url, controller.signal);
        if (generation !== request) return;
        objectUrl = URL.createObjectURL(blob);
        media = document.createElement(!frozen && item.media_type === "video" ? "video" : "img");
        if (media.tagName === "VIDEO") { media.muted = true; media.loop = true; media.playsInline = true; }
        const isVideo = media.tagName === "VIDEO";
        const loaded = waitEvent(media, isVideo ? "loadeddata" : "load", 15000, controller.signal);
        media.src = objectUrl;
        stage.append(media);
        update();
        const useCover = async () => {
          if (generation !== request) return;
          if (!item.cover_url) throw new Error("视频播放失败且没有静态封面");
          const coverBlob = await fetchMediaBlob(item.cover_url, controller.signal);
          if (generation !== request) return;
          if (mediaErrorListener) media.removeEventListener("error", mediaErrorListener);
          mediaErrorListener = null;
          media.pause(); media.removeAttribute("src"); media.load();
          URL.revokeObjectURL(objectUrl);
          objectUrl = URL.createObjectURL(coverBlob);
          media = document.createElement("img"); media.src = objectUrl;
          stage.replaceChildren(media); update();
          report("视频无法播放，已显示静态封面", "danger");
        };
        if (isVideo) {
          try {
            media.load();
            await loaded;
            if (generation !== request) return;
            let timer;
            try {
              await Promise.race([
                media.play(),
                new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("视频播放超时")), 3000); }),
              ]);
            } finally { clearTimeout(timer); }
            if (generation !== request) return;
            mediaErrorListener = () => {
              void useCover().catch((error) => {
                if (generation === request) report(error.message || "静态封面读取失败", "danger");
              });
            };
            media.addEventListener("error", mediaErrorListener, { once: true });
          } catch (error) {
            if (generation !== request || error.name === "AbortError") return;
            await useCover();
            return;
          }
        } else {
          await loaded;
        }
        if (generation !== request) return;
        report(frozen ? "静态封面预览" : "素材预览已打开", "success");
      } catch (error) {
        if (generation === request && error.name !== "AbortError") report(error.message || "预览失败", "danger");
      }
    },
  };
}
