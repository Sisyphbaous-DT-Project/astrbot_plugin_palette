const bridge = window.AstrBotPluginPage;

const form = document.getElementById("settings-form");
const statusText = document.getElementById("status-text");
const statusList = document.getElementById("status-list");
const refreshButton = document.getElementById("refresh");
const saveButton = document.getElementById("save");
const recalculateThemeButton = document.getElementById("recalculate-theme");
const enabledInput = document.getElementById("enabled");
const autoThemeInput = document.getElementById("auto-theme-enabled");
const fileInput = document.getElementById("background-file");
const backgroundName = document.getElementById("background-name");
const fitInput = document.getElementById("background-fit");
const positionInput = document.getElementById("background-position");
const blurInput = document.getElementById("background-blur");
const dimInput = document.getElementById("background-dim");
const surfaceInput = document.getElementById("surface-opacity");
const textModeInput = document.getElementById("text-enhancement-mode");
const textStrengthInput = document.getElementById("text-enhancement-strength");
const grayscaleInput = document.getElementById("background-grayscale");
const brightnessInput = document.getElementById("background-brightness");
const contrastInput = document.getElementById("background-contrast");
const saturationInput = document.getElementById("background-saturation");
const blurValue = document.getElementById("blur-value");
const dimValue = document.getElementById("dim-value");
const surfaceValue = document.getElementById("surface-value");
const textStrengthValue = document.getElementById("text-strength-value");
const grayscaleValue = document.getElementById("grayscale-value");
const brightnessValue = document.getElementById("brightness-value");
const contrastValue = document.getElementById("contrast-value");
const saturationValue = document.getElementById("saturation-value");
const advancedCssInput = document.getElementById("advanced-css");
const preview = document.getElementById("preview");
const previewImage = document.getElementById("preview-image");
const themePrimarySwatch = document.getElementById("theme-primary-swatch");
const themeSecondarySwatch = document.getElementById("theme-secondary-swatch");
const themePrimaryValue = document.getElementById("theme-primary-value");
const themeSecondaryValue = document.getElementById("theme-secondary-value");

let currentConfig = null;
let localPreviewUrl = "";
let remotePreviewDataUrl = "";

function applyThemeFromContext(context) {
  const fallbackTheme = new URLSearchParams(window.location.search).get("theme");
  const isDark = typeof context?.isDark === "boolean"
    ? context.isDark
    : fallbackTheme === "dark";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
}

function clearLocalPreview() {
  if (!localPreviewUrl) {
    return;
  }
  URL.revokeObjectURL(localPreviewUrl);
  localPreviewUrl = "";
}

function setBusy(isBusy) {
  saveButton.disabled = isBusy;
  refreshButton.disabled = isBusy;
  recalculateThemeButton.disabled = isBusy || !currentConfig?.background_image;
  fileInput.disabled = isBusy;
}

function setStatus(message, tone = "muted") {
  statusText.textContent = message;
  statusText.dataset.tone = tone;
}

function notifyPaletteRefresh() {
  window.parent?.postMessage(
    { type: "astrbot-palette:refresh" },
    window.location.origin,
  );
}

async function loadRemotePreview(config) {
  remotePreviewDataUrl = "";
  if (!config?.background_image) {
    updatePreview();
    return;
  }

  try {
    const previewResponse = await bridge.apiGet("background-preview");
    if (previewResponse?.background_image === config.background_image) {
      remotePreviewDataUrl = previewResponse.data_url || "";
    }
  } catch (error) {
    console.warn("[AstrBot调色盘] 壁纸预览读取失败：", error);
  }
  updatePreview();
}

function renderList(target, rows) {
  target.replaceChildren(
    ...rows.map(([label, value]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = String(value ?? "");
      row.append(dt, dd);
      return row;
    }),
  );
}

function configFromForm() {
  return {
    enabled: enabledInput.checked,
    background_image: currentConfig?.background_image || "",
    background_fit: fitInput.value,
    background_position: positionInput.value,
    background_blur: Number.parseInt(blurInput.value, 10) || 0,
    background_dim: Number.parseFloat(dimInput.value) || 0,
    surface_opacity: Number.parseFloat(surfaceInput.value) || 0,
    text_enhancement_mode: textModeInput.value,
    text_enhancement_strength: numberFromInput(textStrengthInput, 0),
    background_grayscale: numberFromInput(grayscaleInput, 0),
    background_brightness: numberFromInput(brightnessInput, 1),
    background_contrast: numberFromInput(contrastInput, 1),
    background_saturation: numberFromInput(saturationInput, 1),
    auto_theme_enabled: autoThemeInput.checked,
    theme_primary: currentConfig?.theme_primary || "",
    theme_secondary: currentConfig?.theme_secondary || "",
    advanced_css: advancedCssInput.value,
  };
}

function applyForm(config) {
  currentConfig = { ...config };
  enabledInput.checked = Boolean(config.enabled);
  fitInput.value = config.background_fit || "cover";
  positionInput.value = config.background_position || "center center";
  blurInput.value = String(config.background_blur ?? 0);
  dimInput.value = String(config.background_dim ?? 0.5);
  surfaceInput.value = String(config.surface_opacity ?? 0);
  textModeInput.value = config.text_enhancement_mode || "soft_shadow";
  textStrengthInput.value = String(config.text_enhancement_strength ?? 1);
  grayscaleInput.value = String(config.background_grayscale ?? 0);
  brightnessInput.value = String(config.background_brightness ?? 1);
  contrastInput.value = String(config.background_contrast ?? 1);
  saturationInput.value = String(config.background_saturation ?? 1);
  autoThemeInput.checked = config.auto_theme_enabled !== false;
  advancedCssInput.value = config.advanced_css || "";
  backgroundName.textContent = config.background_image || "未设置";
  syncThemeColorPreview(config);
  syncRangeLabels();
  updatePreview();
  recalculateThemeButton.disabled = !currentConfig?.background_image;
}

function syncRangeLabels() {
  blurValue.textContent = `${blurInput.value}px`;
  dimValue.textContent = `${Math.round(Number(dimInput.value) * 100)}%`;
  surfaceValue.textContent = `${Math.round(Number(surfaceInput.value) * 100)}%`;
  textStrengthValue.textContent = `${Math.round(Number(textStrengthInput.value) * 100)}%`;
  grayscaleValue.textContent = `${Math.round(Number(grayscaleInput.value) * 100)}%`;
  brightnessValue.textContent = `${Math.round(Number(brightnessInput.value) * 100)}%`;
  contrastValue.textContent = `${Math.round(Number(contrastInput.value) * 100)}%`;
  saturationValue.textContent = `${Math.round(Number(saturationInput.value) * 100)}%`;
}

function updatePreview() {
  const config = configFromForm();
  const imageUrl = localPreviewUrl || remotePreviewDataUrl || "";

  preview.style.setProperty("--preview-fit", config.background_fit);
  preview.style.setProperty("--preview-position", config.background_position);
  preview.style.setProperty("--preview-blur", `${config.background_blur}px`);
  preview.style.setProperty(
    "--preview-inset",
    `${config.background_blur > 0 ? config.background_blur + 16 : 0}px`,
  );
  preview.style.setProperty("--preview-filter", buildBackgroundFilter(config));
  preview.style.setProperty("--preview-dim", String(config.background_dim));
  preview.style.setProperty(
    "--preview-text-shadow",
    buildPreviewTextShadow(config),
  );
  preview.classList.toggle("is-disabled", !config.enabled);
  preview.classList.toggle("has-image", Boolean(imageUrl));
  previewImage.src = imageUrl || "";
  previewImage.style.objectFit = config.background_fit;
  previewImage.style.objectPosition = config.background_position;
  previewImage.alt = imageUrl ? "当前背景预览" : "";
}

function buildBackgroundFilter(config) {
  const filters = [];
  if (config.background_blur > 0) {
    filters.push(`blur(${config.background_blur}px)`);
  }
  if (config.background_grayscale > 0) {
    filters.push(`grayscale(${formatCssNumber(config.background_grayscale)})`);
  }
  if (config.background_brightness !== 1) {
    filters.push(`brightness(${formatCssNumber(config.background_brightness)})`);
  }
  if (config.background_contrast !== 1) {
    filters.push(`contrast(${formatCssNumber(config.background_contrast)})`);
  }
  if (config.background_saturation !== 1) {
    filters.push(`saturate(${formatCssNumber(config.background_saturation)})`);
  }
  return filters.length ? filters.join(" ") : "none";
}

function buildPreviewTextShadow(config) {
  const strength = config.text_enhancement_strength;
  if (config.text_enhancement_mode === "off" || strength <= 0) {
    return "none";
  }
  if (config.text_enhancement_mode === "stroke") {
    const dark = formatCssNumber(0.16 + 0.44 * strength);
    const light = formatCssNumber(0.08 + 0.16 * strength);
    return [
      `0 1px 2px rgba(0, 0, 0, ${dark})`,
      `0 -1px 1px rgba(255, 255, 255, ${light})`,
      `1px 0 1px rgba(0, 0, 0, ${dark})`,
      `-1px 0 1px rgba(0, 0, 0, ${dark})`,
    ].join(", ");
  }
  const dark = formatCssNumber(0.12 + 0.26 * strength);
  const light = formatCssNumber(0.06 + 0.14 * strength);
  const blur = formatCssNumber(1 + 4 * strength);
  return [
    `0 1px ${blur}px rgba(0, 0, 0, ${dark})`,
    `0 -1px ${blur}px rgba(255, 255, 255, ${light})`,
  ].join(", ");
}

function formatCssNumber(value) {
  return Number(value.toFixed(3)).toString();
}

function numberFromInput(input, fallback) {
  const value = Number.parseFloat(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function renderStatus(status, config) {
  renderList(statusList, [
    ["插件", `${status.plugin?.name || "unknown"} ${status.plugin?.version || ""}`],
    ["美化", config.enabled ? "已启用" : "未启用"],
    ["主题色", config.auto_theme_enabled ? "自动同步" : "未同步"],
    ["主色", config.theme_primary || "未生成"],
    ["辅色", config.theme_secondary || "未生成"],
    ["注入", status.injection?.message || "未知"],
    ["图片", config.background_image || "未设置"],
  ]);
}

function syncThemeColorPreview(config) {
  const primary = normalizeHexColor(config.theme_primary);
  const secondary = normalizeHexColor(config.theme_secondary);
  setColorSwatch(themePrimarySwatch, themePrimaryValue, primary);
  setColorSwatch(themeSecondarySwatch, themeSecondaryValue, secondary);
}

function setColorSwatch(swatch, label, color) {
  swatch.style.background = color || "transparent";
  swatch.classList.toggle("is-empty", !color);
  label.textContent = color || "未生成";
}

function normalizeHexColor(value) {
  if (typeof value !== "string") {
    return "";
  }
  const color = value.trim();
  return /^#[0-9a-fA-F]{6}$/.test(color) ? color.toLowerCase() : "";
}

async function loadPaletteState() {
  setBusy(true);
  setStatus("正在读取当前设置");
  try {
    const context = await bridge.ready();
    applyThemeFromContext(context);
    const [status, config] = await Promise.all([
      bridge.apiGet("status"),
      bridge.apiGet("config"),
    ]);
    clearLocalPreview();
    applyForm(config);
    await loadRemotePreview(config);
    renderStatus(status, config);
    setStatus("设置已同步", "success");
  } catch (error) {
    setStatus(error?.message || "读取失败", "danger");
    renderList(statusList, [["错误", error?.message || "读取失败"]]);
  } finally {
    setBusy(false);
  }
}

async function saveConfig() {
  setBusy(true);
  setStatus("正在保存设置");
  try {
    const response = await bridge.apiPost("config", configFromForm());
    clearLocalPreview();
    applyForm(response.config);
    await loadRemotePreview(response.config);
    notifyPaletteRefresh();
    setStatus(response.message || "设置已保存", "success");
  } catch (error) {
    setStatus(error?.message || "保存失败", "danger");
  } finally {
    setBusy(false);
  }
}

async function uploadBackground(file) {
  if (!file) {
    return;
  }
  if (!file.type.startsWith("image/")) {
    setStatus("请选择图片文件", "danger");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    setStatus("图片不能超过 10MB", "danger");
    return;
  }

  clearLocalPreview();
  localPreviewUrl = URL.createObjectURL(file);
  backgroundName.textContent = file.name;
  updatePreview();

  setBusy(true);
  setStatus("正在上传背景图片");
  try {
    const response = await bridge.upload("upload-background", file);
    clearLocalPreview();
    applyForm(response.config);
    await loadRemotePreview(response.config);
    notifyPaletteRefresh();
    setStatus(response.message || "背景图片已上传", "success");
  } catch (error) {
    clearLocalPreview();
    if (currentConfig) {
      applyForm(currentConfig);
    }
    setStatus(error?.message || "上传失败", "danger");
  } finally {
    setBusy(false);
    fileInput.value = "";
  }
}

async function recalculateThemeColors() {
  if (!currentConfig?.background_image) {
    setStatus("请先上传背景图片", "danger");
    return;
  }
  setBusy(true);
  setStatus("正在重新读取壁纸主题色");
  try {
    const response = await bridge.apiPost("theme-colors/recalculate", {});
    applyForm(response.config);
    notifyPaletteRefresh();
    setStatus(response.message || "主题色已重新读取", "success");
  } catch (error) {
    setStatus(error?.message || "主题色读取失败", "danger");
  } finally {
    setBusy(false);
  }
}

refreshButton.addEventListener("click", () => {
  void loadPaletteState();
});

saveButton.addEventListener("click", () => {
  void saveConfig();
});

recalculateThemeButton.addEventListener("click", () => {
  void recalculateThemeColors();
});

fileInput.addEventListener("change", () => {
  void uploadBackground(fileInput.files?.[0]);
});

form.addEventListener("input", () => {
  syncRangeLabels();
  updatePreview();
});

window.addEventListener("beforeunload", () => {
  clearLocalPreview();
});

bridge.onContext((context) => {
  applyThemeFromContext(context);
});

applyThemeFromContext();
void loadPaletteState();
