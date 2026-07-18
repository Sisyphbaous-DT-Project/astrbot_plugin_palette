import { initLiquidGlass } from "./liquid-glass.js";

const bridge = window.AstrBotPluginPage;

const form = document.getElementById("settings-form");
const statusText = document.getElementById("status-text");
const statusList = document.getElementById("status-list");
const refreshButton = document.getElementById("refresh");
const saveButton = document.getElementById("save");
const recalculateThemeButton = document.getElementById("recalculate-theme");
const enabledInput = document.getElementById("enabled");
const autoThemeInput = document.getElementById("auto-theme-enabled");
const detailedTokenStatsInput = document.getElementById("detailed-token-stats-enabled");
const randomBackgroundInput = document.getElementById("random-background-on-load");
const orientationInputs = {
  landscape: document.getElementById("landscape-background-file"),
  portrait: document.getElementById("portrait-background-file"),
};
const orientationNames = {
  landscape: document.getElementById("landscape-background-name"),
  portrait: document.getElementById("portrait-background-name"),
};
const orientationGalleries = {
  landscape: document.getElementById("landscape-background-gallery"),
  portrait: document.getElementById("portrait-background-gallery"),
};
const previewOrientationButtons = Array.from(document.querySelectorAll("[data-preview-orientation]"));
const fitInput = document.getElementById("background-fit");
const positionInput = document.getElementById("background-position");
const blurInput = document.getElementById("background-blur");
const dimInput = document.getElementById("background-dim");
const surfaceInput = document.getElementById("surface-opacity");
const statsCardBlurInput = document.getElementById("stats-card-blur");
const textModeInput = document.getElementById("text-enhancement-mode");
const textStrengthInput = document.getElementById("text-enhancement-strength");
const grayscaleInput = document.getElementById("background-grayscale");
const brightnessInput = document.getElementById("background-brightness");
const contrastInput = document.getElementById("background-contrast");
const saturationInput = document.getElementById("background-saturation");
const blurValue = document.getElementById("blur-value");
const dimValue = document.getElementById("dim-value");
const surfaceValue = document.getElementById("surface-value");
const statsCardBlurValue = document.getElementById("stats-card-blur-value");
const textStrengthValue = document.getElementById("text-strength-value");
const grayscaleValue = document.getElementById("grayscale-value");
const brightnessValue = document.getElementById("brightness-value");
const contrastValue = document.getElementById("contrast-value");
const saturationValue = document.getElementById("saturation-value");
const advancedCssInput = document.getElementById("advanced-css");
const effectPreviews = Array.from(document.querySelectorAll(".effect-preview"));
const themePrimarySwatch = document.getElementById("theme-primary-swatch");
const themeSecondarySwatch = document.getElementById("theme-secondary-swatch");
const themePrimaryValue = document.getElementById("theme-primary-value");
const themeSecondaryValue = document.getElementById("theme-secondary-value");
const tabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
const tabbar = document.querySelector(".tabbar");
const tabbarGlider = document.createElement("span");

let currentConfig = null;
let latestStatus = null;
let localPreviewUrl = "";
let localPreviewOrientation = "";
let remotePreviewDataUrl = "";
let previewOrientation = window.innerHeight > window.innerWidth ? "portrait" : "landscape";
let pendingDeleteFilename = "";
let pendingDeleteOrientation = "";
let pendingDeleteTimer = 0;
const previewCache = new Map();
const customSelects = new Map();
let customSelectListenersReady = false;
const liquidGlass = initLiquidGlass();

function applyThemeFromContext(context) {
  const fallbackTheme = new URLSearchParams(window.location.search).get("theme");
  const isDark = typeof context?.isDark === "boolean"
    ? context.isDark
    : fallbackTheme === "dark";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
}

function activateTab(tabName, focusButton = false) {
  const targetButton = tabButtons.find((button) => button.dataset.tab === tabName);
  const targetPanel = tabPanels.find((panel) => panel.dataset.tabPanel === tabName);
  if (!targetButton || !targetPanel) {
    return;
  }

  tabButtons.forEach((button) => {
    const isActive = button === targetButton;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
  });

  tabPanels.forEach((panel) => {
    const isActive = panel === targetPanel;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });

  customSelects.forEach((_, select) => closeCustomSelect(select));
  updateTabGlider();
  window.requestAnimationFrame(() => liquidGlass.refreshTargets());

  if (tabName === "gallery") {
    updatePreview();
  }

  if (focusButton) {
    targetButton.focus();
  }
}

function initTabs() {
  tabbarGlider.className = "tabbar-glider";
  tabbarGlider.setAttribute("aria-hidden", "true");
  tabbar?.prepend(tabbarGlider);

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activateTab(button.dataset.tab || "gallery");
    });

    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        return;
      }
      event.preventDefault();

      const currentIndex = tabButtons.indexOf(button);
      let nextIndex = currentIndex;
      if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = tabButtons.length - 1;
      } else {
        const direction = event.key === "ArrowRight" ? 1 : -1;
        nextIndex = (currentIndex + direction + tabButtons.length) % tabButtons.length;
      }

      activateTab(tabButtons[nextIndex]?.dataset.tab || "gallery", true);
    });
  });

  const activeButton = tabButtons.find((button) => {
    return button.classList.contains("is-active") || button.getAttribute("aria-selected") === "true";
  });
  activateTab(activeButton?.dataset.tab || "gallery");
  window.addEventListener("resize", updateTabGlider, { passive: true });
}

function updateTabGlider() {
  const activeButton = tabButtons.find((button) => button.classList.contains("is-active"));
  if (!activeButton || !tabbar) {
    return;
  }
  const tabbarRect = tabbar.getBoundingClientRect();
  const buttonRect = activeButton.getBoundingClientRect();
  const x = buttonRect.left - tabbarRect.left;
  const y = buttonRect.top - tabbarRect.top;
  tabbar.style.setProperty("--tabbar-glider-x", `${x}px`);
  tabbar.style.setProperty("--tabbar-glider-y", `${y}px`);
  tabbar.style.setProperty("--tabbar-glider-w", `${buttonRect.width}px`);
  tabbar.style.setProperty("--tabbar-glider-h", `${buttonRect.height}px`);
}

function initCustomSelects(selects) {
  selects.filter(Boolean).forEach((select) => {
    if (customSelects.has(select)) {
      return;
    }

    select.classList.add("native-select-hidden");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    const wrapper = document.createElement("div");
    wrapper.className = "custom-select";

    const trigger = document.createElement("button");
    trigger.className = "custom-select-trigger";
    trigger.type = "button";
    const label = getSelectLabel(select);
    trigger.setAttribute("aria-label", label);
    trigger.setAttribute("aria-controls", `${select.id}-custom-listbox`);
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");

    const value = document.createElement("span");
    value.className = "custom-select-value";
    trigger.append(value);

    const menu = document.createElement("div");
    menu.className = "custom-select-menu";
    menu.id = `${select.id}-custom-listbox`;
    menu.hidden = true;
    menu.role = "listbox";
    menu.tabIndex = -1;

    Array.from(select.options).forEach((option) => {
      const item = document.createElement("button");
      item.className = "custom-select-option";
      item.type = "button";
      item.role = "option";
      item.dataset.value = option.value;
      item.textContent = option.textContent || option.value;
      menu.append(item);
    });

    wrapper.append(trigger, menu);
    select.after(wrapper);
    customSelects.set(select, { select, wrapper, trigger, value, menu, label });
    liquidGlass.refreshTargets();

    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleCustomSelect(select);
    });

    trigger.addEventListener("keydown", (event) => {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        openCustomSelect(select, event.key === "ArrowUp" ? "last" : "selected");
      }
    });

    menu.addEventListener("click", (event) => {
      const option = event.target.closest(".custom-select-option");
      if (!option || !menu.contains(option)) {
        return;
      }
      event.preventDefault();
      chooseCustomSelectValue(select, option.dataset.value || "");
    });

    menu.addEventListener("keydown", (event) => {
      handleCustomSelectMenuKeydown(select, event);
    });

    wrapper.addEventListener("focusout", () => {
      window.setTimeout(() => {
        if (!wrapper.contains(document.activeElement)) {
          closeCustomSelect(select);
        }
      }, 0);
    });

    select.addEventListener("input", () => {
      syncCustomSelect(select);
    });
    select.addEventListener("change", () => {
      syncCustomSelect(select);
    });

    syncCustomSelect(select);
  });

  if (!customSelectListenersReady) {
    document.addEventListener("click", (event) => {
      customSelects.forEach((state, select) => {
        if (!state.wrapper.contains(event.target)) {
          closeCustomSelect(select);
        }
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        customSelects.forEach((_, select) => closeCustomSelect(select));
      }
    });

    customSelectListenersReady = true;
  }
}

function getSelectLabel(select) {
  const labelText = select
    .closest("label")
    ?.querySelector("span")
    ?.textContent
    ?.replace(/\s+/g, " ")
    .trim();
  return labelText || select.name || select.id || "选项";
}

function toggleCustomSelect(select) {
  const state = customSelects.get(select);
  if (!state) {
    return;
  }
  if (state.wrapper.classList.contains("is-open")) {
    closeCustomSelect(select);
    return;
  }
  openCustomSelect(select, "selected");
}

function openCustomSelect(select, focusMode = "selected") {
  const state = customSelects.get(select);
  if (!state) {
    return;
  }

  customSelects.forEach((_, otherSelect) => {
    if (otherSelect !== select) {
      closeCustomSelect(otherSelect);
    }
  });

  state.wrapper.classList.add("is-open");
  state.wrapper.closest("label")?.classList.add("is-select-open");
  state.wrapper.closest(".panel-block")?.classList.add("has-open-select");
  state.trigger.setAttribute("aria-expanded", "true");
  state.menu.hidden = false;

  const options = getCustomSelectOptions(state);
  const selected = options.find((option) => option.dataset.value === select.value);
  const target = focusMode === "last" ? options.at(-1) : selected || options[0];
  window.requestAnimationFrame(() => {
    target?.focus();
  });
}

function closeCustomSelect(select) {
  const state = customSelects.get(select);
  if (!state) {
    return;
  }
  state.wrapper.classList.remove("is-open");
  state.wrapper.closest("label")?.classList.remove("is-select-open");
  state.wrapper.closest(".panel-block")?.classList.remove("has-open-select");
  state.trigger.setAttribute("aria-expanded", "false");
  state.menu.hidden = true;
}

function chooseCustomSelectValue(select, value) {
  if (select.value !== value) {
    select.value = value;
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }
  syncCustomSelect(select);
  closeCustomSelect(select);
  customSelects.get(select)?.trigger.focus();
}

function handleCustomSelectMenuKeydown(select, event) {
  const state = customSelects.get(select);
  if (!state) {
    return;
  }

  const options = getCustomSelectOptions(state);
  const currentIndex = options.indexOf(document.activeElement);
  const focusOption = (index) => {
    if (!options.length) {
      return;
    }
    const next = options.at((index + options.length) % options.length);
    next?.focus();
  };

  if (event.key === "Tab") {
    closeCustomSelect(select);
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    focusOption(currentIndex + 1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    focusOption(currentIndex - 1);
    return;
  }
  if (event.key === "Home") {
    event.preventDefault();
    options[0]?.focus();
    return;
  }
  if (event.key === "End") {
    event.preventDefault();
    options.at(-1)?.focus();
    return;
  }
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    const option = document.activeElement?.closest(".custom-select-option");
    if (option) {
      chooseCustomSelectValue(select, option.dataset.value || "");
    }
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeCustomSelect(select);
    state.trigger.focus();
  }
}

function getCustomSelectOptions(state) {
  return Array.from(state.menu.querySelectorAll(".custom-select-option"));
}

function syncCustomSelect(select) {
  const state = customSelects.get(select);
  if (!state) {
    return;
  }

  const selectedOption = Array.from(select.options).find((option) => {
    return option.value === select.value;
  });
  const selectedText = selectedOption?.textContent || select.value || "请选择";
  state.value.textContent = selectedText;
  state.trigger.setAttribute("aria-label", `${state.label}：${selectedText}`);

  getCustomSelectOptions(state).forEach((option) => {
    const isSelected = option.dataset.value === select.value;
    option.classList.toggle("is-selected", isSelected);
    option.setAttribute("aria-selected", String(isSelected));
  });
}

function clearLocalPreview() {
  if (!localPreviewUrl) {
    return;
  }
  URL.revokeObjectURL(localPreviewUrl);
  localPreviewUrl = "";
  localPreviewOrientation = "";
}

function setBusy(isBusy) {
  saveButton.disabled = isBusy;
  refreshButton.disabled = isBusy;
  recalculateThemeButton.disabled = isBusy || !getThemeBackgroundFilename(currentConfig);
  Object.values(orientationInputs).forEach((input) => {
    if (input) {
      input.disabled = isBusy;
    }
  });
  Object.values(orientationGalleries)
    .flatMap((gallery) => Array.from(gallery?.querySelectorAll("button") || []))
    .forEach((button) => {
      button.disabled = isBusy;
    });
}

function setStatus(message, tone = "muted") {
  statusText.textContent = message;
  statusText.dataset.tone = tone;
}

function clearPendingDelete() {
  pendingDeleteFilename = "";
  pendingDeleteOrientation = "";
  if (pendingDeleteTimer) {
    window.clearTimeout(pendingDeleteTimer);
    pendingDeleteTimer = 0;
  }
  Object.values(orientationGalleries).forEach((gallery) => {
    gallery?.querySelectorAll(".gallery-delete").forEach((button) => {
      button.classList.remove("is-confirming");
      button.textContent = "删除";
    });
  });
}

function notifyPaletteRefresh() {
  window.parent?.postMessage(
    { type: "astrbot-palette:refresh" },
    window.location.origin,
  );
}

async function loadRemotePreview(config) {
  remotePreviewDataUrl = "";
  const filename = getPreviewBackgroundFilename(config);
  if (!filename) {
    updatePreview();
    return;
  }

  try {
    remotePreviewDataUrl = await getThumbnailDataUrl(filename);
  } catch (error) {
    console.warn("[AstrBot调色盘] 壁纸预览读取失败：", error);
  }
  updatePreview();
}

async function getThumbnailDataUrl(filename) {
  if (!filename) {
    return "";
  }
  if (previewCache.has(filename)) {
    return previewCache.get(filename);
  }
  const thumbnailResponse = await bridge.apiGet("background-thumbnail", { filename });
  const dataUrl = thumbnailResponse?.data_url || "";
  if (dataUrl) {
    previewCache.set(filename, dataUrl);
  }
  return dataUrl;
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
    background_images: Array.isArray(currentConfig?.background_images)
      ? currentConfig.background_images
      : [],
    landscape_background_image: currentConfig?.landscape_background_image || "",
    landscape_background_images: Array.isArray(currentConfig?.landscape_background_images)
      ? currentConfig.landscape_background_images
      : [],
    portrait_background_image: currentConfig?.portrait_background_image || "",
    portrait_background_images: Array.isArray(currentConfig?.portrait_background_images)
      ? currentConfig.portrait_background_images
      : [],
    background_fit: fitInput.value,
    background_position: positionInput.value,
    background_blur: Number.parseInt(blurInput.value, 10) || 0,
    background_dim: Number.parseFloat(dimInput.value) || 0,
    surface_opacity: Number.parseFloat(surfaceInput.value) || 0,
    stats_card_blur: Number.parseInt(statsCardBlurInput.value, 10) || 0,
    text_enhancement_mode: textModeInput.value,
    text_enhancement_strength: numberFromInput(textStrengthInput, 0),
    background_grayscale: numberFromInput(grayscaleInput, 0),
    background_brightness: numberFromInput(brightnessInput, 1),
    background_contrast: numberFromInput(contrastInput, 1),
    background_saturation: numberFromInput(saturationInput, 1),
    random_background_on_load: randomBackgroundInput.checked,
    auto_theme_enabled: autoThemeInput.checked,
    detailed_token_stats_enabled: detailedTokenStatsInput.checked,
    theme_primary: currentConfig?.theme_primary || "",
    theme_secondary: currentConfig?.theme_secondary || "",
    advanced_css: advancedCssInput.value,
  };
}

function getOrientationConfigKeys(orientation) {
  if (orientation === "portrait") {
    return {
      current: "portrait_background_image",
      items: "portrait_background_items",
      images: "portrait_background_images",
    };
  }
  return {
    current: "landscape_background_image",
    items: "landscape_background_items",
    images: "landscape_background_images",
  };
}

function getPreviewBackgroundFilename(config) {
  if (!config) {
    return "";
  }
  if (previewOrientation === "portrait") {
    return config.portrait_background_image
      || config.background_image
      || config.landscape_background_image
      || "";
  }
  return config.landscape_background_image
    || config.background_image
    || config.portrait_background_image
    || "";
}

function getThemeBackgroundFilename(config) {
  return config?.landscape_background_image
    || config?.portrait_background_image
    || config?.background_image
    || "";
}

function syncPreviewOrientationButtons() {
  previewOrientationButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.previewOrientation === previewOrientation);
  });
}

function applyForm(config) {
  currentConfig = { ...config };
  enabledInput.checked = Boolean(config.enabled);
  fitInput.value = config.background_fit || "cover";
  positionInput.value = config.background_position || "center center";
  blurInput.value = String(config.background_blur ?? 0);
  dimInput.value = String(config.background_dim ?? 0.5);
  surfaceInput.value = String(config.surface_opacity ?? 0);
  statsCardBlurInput.value = String(config.stats_card_blur ?? 14);
  textModeInput.value = config.text_enhancement_mode || "soft_shadow";
  textStrengthInput.value = String(config.text_enhancement_strength ?? 1);
  grayscaleInput.value = String(config.background_grayscale ?? 0);
  brightnessInput.value = String(config.background_brightness ?? 1);
  contrastInput.value = String(config.background_contrast ?? 1);
  saturationInput.value = String(config.background_saturation ?? 1);
  randomBackgroundInput.checked = Boolean(config.random_background_on_load);
  autoThemeInput.checked = config.auto_theme_enabled !== false;
  detailedTokenStatsInput.checked = Boolean(config.detailed_token_stats_enabled);
  advancedCssInput.value = config.advanced_css || "";
  orientationNames.landscape.textContent = config.landscape_background_image || "未设置";
  orientationNames.portrait.textContent = config.portrait_background_image || "未设置";
  syncCustomSelect(fitInput);
  syncCustomSelect(positionInput);
  syncCustomSelect(textModeInput);
  syncThemeColorPreview(config);
  renderGallery(config, "landscape");
  renderGallery(config, "portrait");
  syncPreviewOrientationButtons();
  if (latestStatus) {
    renderStatus(latestStatus, config);
  }
  syncRangeLabels();
  updatePreview();
  recalculateThemeButton.disabled = !getThemeBackgroundFilename(currentConfig);
}

function syncRangeLabels() {
  blurValue.textContent = `${blurInput.value}px`;
  dimValue.textContent = `${Math.round(Number(dimInput.value) * 100)}%`;
  surfaceValue.textContent = `${Math.round(Number(surfaceInput.value) * 100)}%`;
  statsCardBlurValue.textContent = `${statsCardBlurInput.value}px`;
  textStrengthValue.textContent = `${Math.round(Number(textStrengthInput.value) * 100)}%`;
  grayscaleValue.textContent = `${Math.round(Number(grayscaleInput.value) * 100)}%`;
  brightnessValue.textContent = `${Math.round(Number(brightnessInput.value) * 100)}%`;
  contrastValue.textContent = `${Math.round(Number(contrastInput.value) * 100)}%`;
  saturationValue.textContent = `${Math.round(Number(saturationInput.value) * 100)}%`;
}

function updatePreview() {
  const config = configFromForm();
  const imageUrl = localPreviewUrl && localPreviewOrientation === previewOrientation
    ? localPreviewUrl
    : remotePreviewDataUrl || "";

  effectPreviews.forEach((preview) => {
    const image = preview.querySelector(".preview-image");
    preview.style.setProperty("--preview-fit", config.background_fit);
    preview.style.setProperty("--preview-position", config.background_position);
    preview.style.setProperty("--preview-blur", `${config.background_blur}px`);
    preview.style.setProperty(
      "--preview-inset",
      `${config.background_blur > 0 ? config.background_blur + 16 : 0}px`,
    );
    preview.style.setProperty("--preview-filter", buildBackgroundFilter(config));
    preview.style.setProperty("--preview-dim", String(config.background_dim));
    preview.style.setProperty("--preview-surface", String(config.surface_opacity));
    preview.style.setProperty("--preview-surface-fill-top", formatCssNumber(0.02 + config.surface_opacity * 0.18));
    preview.style.setProperty("--preview-surface-fill-bottom", formatCssNumber(0.005 + config.surface_opacity * 0.08));
    preview.style.setProperty("--preview-surface-rim", formatCssNumber(0.16 + config.surface_opacity * 0.24));
    preview.style.setProperty("--preview-surface-shadow", formatCssNumber(0.08 + config.surface_opacity * 0.12));
    preview.style.setProperty("--preview-card-blur", `${config.stats_card_blur}px`);
    preview.style.setProperty(
      "--preview-text-shadow",
      buildPreviewTextShadow(config),
    );
    preview.style.setProperty(
      "--preview-primary",
      normalizeHexColor(config.theme_primary) || "rgba(255, 255, 255, 0.88)",
    );
    preview.style.setProperty(
      "--preview-secondary",
      normalizeHexColor(config.theme_secondary) || "rgba(255, 255, 255, 0.5)",
    );
    preview.classList.toggle("is-disabled", !config.enabled);
    preview.classList.toggle("has-image", Boolean(imageUrl));
    if (image) {
      image.src = imageUrl || "";
      image.style.objectFit = previewObjectFit(config.background_fit);
      image.style.objectPosition = config.background_position;
      image.alt = imageUrl ? "当前背景预览" : "";
    }
  });
  liquidGlass.updateFilter(imageUrl, config);
}

function previewObjectFit(value) {
  if (value === "stretch") {
    return "fill";
  }
  if (value === "auto") {
    return "none";
  }
  return ["cover", "contain"].includes(value) ? value : "cover";
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
  latestStatus = status;
  const injection = status.injection || {};
  const injectionSourceLabels = {
    custom: "自定义 WebUI",
    "data/dist": "data/dist",
    bundled: "内置 WebUI",
  };
  const injectionRows = [
    ["注入", injection.message || "未知"],
    ["目标", injectionSourceLabels[injection.target_source] || injection.target_source || "未知"],
  ];
  if (injection.restart_required) {
    injectionRows.push(["重启", "需要重启 AstrBot 后生效"]);
  }
  renderList(statusList, [
    ["插件", `${status.plugin?.name || "unknown"} ${status.plugin?.version || ""}`],
    ["美化", config.enabled ? "已启用" : "未启用"],
    ["横屏图库", `${config.landscape_background_images?.length || 0} 张`],
    ["竖屏图库", `${config.portrait_background_images?.length || 0} 张`],
    ["预览方向", previewOrientation === "portrait" ? "竖屏" : "横屏"],
    ["随机", config.random_background_on_load ? "打开或刷新时随机" : "关闭"],
    ["主题色", config.auto_theme_enabled ? "自动同步" : "未同步"],
    ["统计增强", config.detailed_token_stats_enabled ? "已启用" : "关闭"],
    ["主色", config.theme_primary || "未生成"],
    ["辅色", config.theme_secondary || "未生成"],
    ...injectionRows,
    ["横屏图片", config.landscape_background_image || "未设置"],
    ["竖屏图片", config.portrait_background_image || "未设置"],
  ]);
}

function renderGallery(config, orientation) {
  const gallery = orientationGalleries[orientation];
  if (!gallery) {
    return;
  }
  const keys = getOrientationConfigKeys(orientation);
  const items = Array.isArray(config[keys.items]) ? config[keys.items] : [];
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "gallery-empty";
    empty.textContent = orientation === "portrait"
      ? "竖屏图库里还没有图片。"
      : "横屏图库里还没有图片。";
    gallery.replaceChildren(empty);
    return;
  }

  gallery.replaceChildren(
    ...items.map((item) => {
      const filename = item.filename || "";
      const tile = document.createElement("article");
      tile.className = "gallery-item";
      tile.classList.toggle("is-selected", filename === config[keys.current]);

      const selectButton = document.createElement("button");
      selectButton.className = "gallery-select";
      selectButton.type = "button";
      selectButton.dataset.galleryAction = "select";
      selectButton.dataset.filename = filename;
      selectButton.dataset.orientation = orientation;
      selectButton.title = "切换到这张背景";

      const image = document.createElement("img");
      image.alt = filename ? `背景缩略图 ${filename}` : "背景缩略图";
      image.loading = "lazy";
      image.decoding = "async";
      selectButton.append(image);

      void hydrateGalleryImage(filename, image);

      const meta = document.createElement("div");
      meta.className = "gallery-meta";

      const name = document.createElement("span");
      name.textContent = filename || "未知图片";

      const deleteButton = document.createElement("button");
      deleteButton.className = "gallery-delete";
      deleteButton.type = "button";
      deleteButton.dataset.galleryAction = "delete";
      deleteButton.dataset.filename = filename;
      deleteButton.dataset.orientation = orientation;
      deleteButton.title = "删除这张背景";
      deleteButton.textContent = "删除";
      deleteButton.classList.toggle(
        "is-confirming",
        filename === pendingDeleteFilename && orientation === pendingDeleteOrientation,
      );
      if (filename === pendingDeleteFilename && orientation === pendingDeleteOrientation) {
        deleteButton.textContent = "确认删除";
      }

      meta.append(name, deleteButton);
      tile.append(selectButton, meta);
      return tile;
    }),
  );
  liquidGlass.refreshTargets();
}

async function hydrateGalleryImage(filename, image) {
  try {
    const dataUrl = await getThumbnailDataUrl(filename);
    if (dataUrl) {
      image.src = dataUrl;
    }
  } catch (error) {
    console.warn("[AstrBot调色盘] 缩略图读取失败：", error);
  }
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
    latestStatus = status;
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

async function uploadBackgroundFiles(files, orientation) {
  const imageFiles = Array.from(files || []);
  if (!imageFiles.length) {
    return;
  }

  let latestConfig = currentConfig;
  let uploadedCount = 0;
  setBusy(true);
  const orientationLabel = orientation === "portrait" ? "竖屏" : "横屏";
  setStatus(`正在上传 ${imageFiles.length} 张${orientationLabel}背景图片`);
  try {
    for (const file of imageFiles) {
      if (!file.type.startsWith("image/")) {
        throw new Error(`请选择图片文件：${file.name}`);
      }
      if (file.size > 10 * 1024 * 1024) {
        throw new Error(`图片不能超过 10MB：${file.name}`);
      }
    }

    for (const file of imageFiles) {
      const response = await bridge.upload(`upload-background/${orientation}`, file);
      latestConfig = response.config;
      uploadedCount += 1;
      setStatus(`已上传 ${uploadedCount}/${imageFiles.length} 张${orientationLabel}背景图片`);
    }
    clearLocalPreview();
    previewCache.clear();
    previewOrientation = orientation;
    applyForm(latestConfig);
    await loadRemotePreview(latestConfig);
    notifyPaletteRefresh();
    setStatus(`已加入${orientationLabel}图库 ${uploadedCount} 张背景图片`, "success");
  } catch (error) {
    clearLocalPreview();
    if (uploadedCount > 0 && latestConfig) {
      applyForm(latestConfig);
      await loadRemotePreview(latestConfig);
      setStatus(
        `已加入${orientationLabel}图库 ${uploadedCount} 张，后续图片上传失败：${error?.message || "上传失败"}`,
        "danger",
      );
    } else if (currentConfig) {
      applyForm(currentConfig);
      setStatus(error?.message || "上传失败", "danger");
    } else {
      setStatus(error?.message || "上传失败", "danger");
    }
  } finally {
    setBusy(false);
    if (orientationInputs[orientation]) {
      orientationInputs[orientation].value = "";
    }
  }
}

async function selectBackground(filename, orientation) {
  const keys = getOrientationConfigKeys(orientation);
  if (!filename || filename === currentConfig?.[keys.current]) {
    return;
  }
  clearPendingDelete();
  setBusy(true);
  setStatus("正在切换背景图片");
  try {
    const response = await bridge.apiPost("backgrounds/select", {
      background_image: filename,
      orientation,
    });
    previewOrientation = orientation;
    applyForm(response.config);
    await loadRemotePreview(response.config);
    notifyPaletteRefresh();
    setStatus(response.message || "背景图片已切换", "success");
  } catch (error) {
    setStatus(error?.message || "切换失败", "danger");
  } finally {
    setBusy(false);
  }
}

function requestDeleteBackground(filename, orientation) {
  if (!filename) {
    return;
  }
  if (pendingDeleteFilename !== filename || pendingDeleteOrientation !== orientation) {
    clearPendingDelete();
    pendingDeleteFilename = filename;
    pendingDeleteOrientation = orientation;
    renderGallery(currentConfig || {}, "landscape");
    renderGallery(currentConfig || {}, "portrait");
    setStatus("再点一次确认删除这张背景图片", "danger");
    pendingDeleteTimer = window.setTimeout(() => {
      clearPendingDelete();
      setStatus("已取消删除确认");
    }, 5000);
    return;
  }

  void deleteBackground(filename, orientation);
}

async function deleteBackground(filename, orientation) {
  if (!filename) {
    return;
  }
  clearPendingDelete();
  setBusy(true);
  setStatus("正在删除背景图片");
  try {
    const response = await bridge.apiPost("backgrounds/delete", {
      background_image: filename,
      orientation,
    });
    previewCache.delete(filename);
    applyForm(response.config);
    await loadRemotePreview(response.config);
    notifyPaletteRefresh();
    setStatus(response.message || "背景图片已删除", "success");
  } catch (error) {
    setStatus(error?.message || "删除失败", "danger");
  } finally {
    setBusy(false);
  }
}

async function recalculateThemeColors() {
  if (!getThemeBackgroundFilename(currentConfig)) {
    setStatus("请先上传背景图片", "danger");
    return;
  }
  setBusy(true);
  setStatus("正在重新读取壁纸主题色");
  try {
    const response = await bridge.apiPost("theme-colors/recalculate", {
      orientation: previewOrientation,
    });
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

Object.entries(orientationInputs).forEach(([orientation, input]) => {
  input?.addEventListener("change", () => {
    void uploadBackgroundFiles(input.files, orientation);
  });
});

Object.values(orientationGalleries).forEach((gallery) => {
  gallery?.addEventListener("pointerdown", (event) => {
    const button = event.target.closest("[data-gallery-action]");
    if (!button || !gallery.contains(button)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
  });

  gallery?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-gallery-action]");
    if (!button || !gallery.contains(button)) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const filename = button.dataset.filename || "";
    const orientation = button.dataset.orientation || gallery.dataset.galleryOrientation || "landscape";
    if (button.dataset.galleryAction === "select") {
      void selectBackground(filename, orientation);
      return;
    }
    if (button.dataset.galleryAction === "delete") {
      requestDeleteBackground(filename, orientation);
    }
  });
});

previewOrientationButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const orientation = button.dataset.previewOrientation || "landscape";
    if (orientation !== "landscape" && orientation !== "portrait") {
      return;
    }
    previewOrientation = orientation;
    syncPreviewOrientationButtons();
    void loadRemotePreview(currentConfig || {});
    if (latestStatus && currentConfig) {
      renderStatus(latestStatus, currentConfig);
    }
  });
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
initTabs();
initCustomSelects([fitInput, positionInput, textModeInput]);
void loadPaletteState();
