import { inspectFile, makeCover } from "./media.js";

const IMAGE_EXTENSIONS = /\.(jpe?g|png|webp)$/i;
const VIDEO_EXTENSIONS = /\.(mp4|webm)$/i;
const EXCLUDED_TYPES = new Set(["scene", "web", "application"]);

export function projectPath(directory, value) {
  if (typeof value !== "string" || !value.trim()) return "";
  const path = value.replaceAll("\\", "/");
  if (/^(?:\/|[a-z][a-z0-9+.-]*:)/i.test(path) || path.split("/").includes("..")) return "";
  const parts = path.split("/").filter((part) => part && part !== ".");
  return parts.length ? `${directory ? `${directory}/` : ""}${parts.join("/")}` : "";
}

export async function scanWallpaperFiles(entries) {
  const files = new Map(entries.map((entry) => [entry.path.replaceAll("\\", "/"), entry.file]));
  const projects = [...files.keys()].filter((path) => /(^|\/)project\.json$/i.test(path));
  const scopes = projects.map((path) => path.slice(0, -12).replace(/\/$/, ""));
  const specialDirectories = new Set(
    [...files.keys()].filter((path) => /\.(pkg|html?|exe)$/i.test(path))
      .map((path) => path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : ""),
  );
  const items = [];
  const skipped = { unsupported: 0, invalid: 0, unknown: 0 };
  for (const project of projects) {
    const directory = project.slice(0, -12).replace(/\/$/, "");
    try {
      const metadata = files.get(project);
      if (metadata.size > 1024 * 1024) throw new Error("项目元信息过大");
      const data = JSON.parse(await metadata.text());
      const type = String(data.type || "").toLowerCase();
      if (EXCLUDED_TYPES.has(type)) { skipped.unsupported += 1; continue; }
      const mainPath = projectPath(directory, data.file);
      const file = files.get(mainPath);
      if (!file) throw new Error("缺少原素材");
      const kind = VIDEO_EXTENSIONS.test(mainPath) ? "video" : IMAGE_EXTENSIONS.test(mainPath) ? "image" : "";
      if (!kind || (type === "video" && kind !== "video") || (type === "image" && kind !== "image") || (type && !["video", "image"].includes(type))) {
        skipped.unknown += 1;
        continue;
      }
      if (!type && specialDirectories.has(directory)) {
        skipped.unknown += 1;
        continue;
      }
      const previewPath = projectPath(directory, data.preview);
      const preview = IMAGE_EXTENSIONS.test(previewPath) ? files.get(previewPath) : null;
      items.push({
        id: mainPath, name: String(data.title || file.name), file, kind,
        preview: preview || (kind === "image" ? file : null), state: "ready",
      });
    } catch (_) { skipped.invalid += 1; }
  }
  for (const [path, file] of files) {
    const inProject = scopes.some((scope) => !scope || path.startsWith(`${scope}/`));
    if (inProject || !IMAGE_EXTENSIONS.test(path)) continue;
    // 没有元信息但带场景包/网页主文件的目录不作为普通图片目录。
    const directory = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
    const parts = directory.split("/");
    const hasSpecial = specialDirectories.has("") || parts.some((_, i) => specialDirectories.has(parts.slice(0, i + 1).join("/")));
    if (hasSpecial) { skipped.unknown += 1; continue; }
    items.push({ id: path, name: file.name, file, kind: "image", preview: file, state: "ready" });
  }
  return { items, skipped };
}

export async function collectDirectory(handle, prefix = "") {
  const entries = [];
  for await (const [name, child] of handle.entries()) {
    const path = prefix ? `${prefix}/${name}` : name;
    if (child.kind === "directory") entries.push(...await collectDirectory(child, path));
    else entries.push({ path, file: await child.getFile() });
  }
  return entries;
}

export async function pickWallpaperDirectory(browser) {
  try {
    const handle = await browser.showDirectoryPicker({ mode: "read", id: "palette-wallpaper-import" });
    // 保留所选根目录名，避免不同项目目录里的同名主文件混为一项。
    return await collectDirectory(handle, handle.name || "");
  } catch (error) {
    if (error.name === "AbortError") return null;
    throw error;
  }
}

export async function importWallpaperItem(item, orientation, upload) {
  if (item.state === "imported" || item.state === "uploading") return false;
  item.state = "uploading";
  try {
    await upload(item.file, orientation);
    item.state = "imported";
    item.orientation = orientation;
    item.error = "";
    return true;
  } catch (error) {
    item.state = "failed";
    item.error = error?.message || "导入失败，可重试";
    return false;
  }
}

export function createWallpaperImportSession() {
  const imported = new Map();
  const identity = (item) => JSON.stringify([
    item.id, item.file.name, item.file.size, item.file.lastModified,
  ]);
  return {
    remember(item) {
      if (item.state === "imported") imported.set(identity(item), item.orientation);
    },
    restore(items) {
      for (const item of items) {
        const key = identity(item);
        if (imported.has(key)) {
          item.state = "imported";
          item.orientation = imported.get(key);
          item.error = "";
        }
      }
    },
  };
}

export function initWallpaperImport(panel, upload, report) {
  const list = panel.querySelector(".wallpaper-import-list");
  const input = panel.querySelector("[data-directory-input]");
  const orientation = panel.querySelector("[data-import-orientation]");
  const directoryButton = panel.querySelector("[data-select-directory]");
  const summary = panel.querySelector(".wallpaper-import-summary");
  let result = { items: [], skipped: {} };
  let generation = 0;
  let busy = false;
  const session = createWallpaperImportSession();
  const previewObservers = new Set();
  const previewUrls = new Set();
  const releasePreviews = () => {
    previewObservers.forEach((observer) => observer.disconnect()); previewObservers.clear();
    previewUrls.forEach((url) => URL.revokeObjectURL(url)); previewUrls.clear();
  };
  const close = () => {
    generation += 1;
    releasePreviews();
    panel.hidden = true;
    list.replaceChildren();
  };
  function updateActions() {
    directoryButton.disabled = busy;
    orientation.disabled = busy;
    panel.querySelector("[data-directory-fallback]").disabled = busy;
    for (const button of list.querySelectorAll(".wallpaper-import-action")) {
      const item = button.__paletteImportItem;
      button.textContent = item.state === "imported"
        ? `已导入${item.orientation === "portrait" ? "竖屏" : "横屏"}`
        : item.state === "uploading" ? "导入中"
          : item.state === "failed" ? "重试" : "导入";
      button.disabled = busy || item.state === "imported";
      button.parentNode.querySelector(".import-error").textContent = item.error || "";
    }
  }
  function render() {
    const request = ++generation;
    releasePreviews();
    list.replaceChildren(...result.items.map((item) => {
      const row = document.createElement("article");
      row.className = "wallpaper-import-item";
      const image = document.createElement("img");
      image.alt = ""; image.loading = "lazy";
      const description = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = item.name;
      const detail = document.createElement("small");
      detail.textContent = `${item.kind === "video" ? "视频" : "图片"} · ${(item.file.size / 1024 / 1024).toFixed(1)}MiB`;
      const error = document.createElement("small"); error.className = "import-error"; error.textContent = item.error || "";
      description.append(title, detail, error);
      const button = document.createElement("button"); button.type = "button";
      button.className = "ghost-button wallpaper-import-action";
      button.__paletteImportItem = item;
      button.addEventListener("click", async () => {
        if (busy) return;
        busy = true;
        const importing = importWallpaperItem(item, orientation.value, upload);
        updateActions();
        await importing;
        session.remember(item);
        busy = false;
        // 只更新状态按钮，保留已生成的预览和对象 URL。
        updateActions();
      });
      row.append(image, description, button);
      if (item.preview && item.preview.size <= 4 * 1024 * 1024) {
        // 仅可见列表项按需解码小预览，不读取整段视频。
        const observer = new IntersectionObserver(async (entries) => {
          if (!entries.some((entry) => entry.isIntersecting)) return;
          observer.disconnect();
          try {
            const info = await inspectFile(item.preview);
            if (info.kind !== "image") return;
            const cover = await makeCover(item.preview, info);
            if (generation !== request || !row.isConnected || panel.hidden) return;
            const url = URL.createObjectURL(cover); previewUrls.add(url); image.src = url;
          } catch (_) { /* 无预览时保留类型占位。 */ }
        });
        observer.observe(row);
        previewObservers.add(observer);
      }
      return row;
    }));
    updateActions();
    const skipped = Object.values(result.skipped).reduce((sum, value) => sum + value, 0);
    summary.textContent = `可导入 ${result.items.length} 项 · 跳过 ${skipped} 项（专用类型 ${result.skipped.unsupported || 0}，损坏/缺失 ${result.skipped.invalid || 0}，用途不明 ${result.skipped.unknown || 0}）`;
  }
  async function scan(entries) {
    const request = ++generation;
    report("正在识别本地壁纸素材");
    try {
      const next = await scanWallpaperFiles(entries);
      if (generation !== request) return;
      session.restore(next.items);
      result = next;
      panel.hidden = false;
      render();
      report(`识别完成，可导入 ${result.items.length} 项`, "success");
    } catch (error) { report(error.message || "目录读取失败", "danger"); }
  }
  input.addEventListener("change", () => {
    if (!input.files.length) return;
    const entries = [...input.files].map((file) => ({ path: file.webkitRelativePath || file.name, file }));
    input.value = "";
    void scan(entries);
  });
  directoryButton.addEventListener("click", async () => {
    if (busy) return;
    if (window.isSecureContext && typeof window.showDirectoryPicker === "function") {
      const request = generation;
      try {
        const entries = await pickWallpaperDirectory(window);
        if (entries === null || generation !== request) return;
        await scan(entries);
        return;
      } catch (error) {
        if (error.name === "AbortError") return;
        report("当前环境无法使用目录授权，可点“选择目录（兼容方式）”");
        return;
      }
    }
    if ("webkitdirectory" in input) input.click();
    else report("当前浏览器不支持目录选择，请使用图库的普通文件上传入口", "danger");
  });
  panel.querySelector("[data-directory-fallback]").addEventListener("click", () => {
    if (busy) return;
    if ("webkitdirectory" in input) input.click();
    else report("当前浏览器不支持目录选择，请使用普通文件上传", "danger");
  });
  panel.querySelector("[data-close-import]").addEventListener("click", close);
  window.addEventListener("pagehide", () => { generation += 1; releasePreviews(); });
  return {
    open() { panel.hidden = false; render(); },
    close,
  };
}
