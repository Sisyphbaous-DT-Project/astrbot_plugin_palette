/**
 * Liquid Glass controller for AstrBot Palette settings page.
 *
 * Uses a full-screen WebGL canvas behind the page content to draw the
 * wallpaper background and edge-only refractive highlights. Large content
 * panels keep their center transparent to avoid blocky sampling artifacts.
 */

const FALLBACK_CLASS = "liquid-glass-fallback";
const ACTIVE_CLASS = "liquid-glass-active";

const GLASS_SELECTORS = [
  ".custom-select-trigger",
  ".gallery-item.is-selected",
];

export function initLiquidGlass() {
  if (ensureWebGLSupport()) {
    document.body.classList.add(ACTIVE_CLASS);
    const renderer = initWebGLRenderer();
    return {
      refreshTargets: () => renderer.refreshTargets(),
      updateFilter: (imageUrl, config) => renderer.update(imageUrl, config),
      pulse: () => {},
      destroy: () => renderer.destroy(),
    };
  }

  document.body.classList.add(FALLBACK_CLASS);
  const fallback = initCssFallback();
  return {
    refreshTargets: () => {},
    updateFilter: (imageUrl, config) => fallback.updateFromConfig(config),
    pulse: () => {},
    destroy: () => fallback.destroy(),
  };
}

function ensureWebGLSupport() {
  const canvas = document.createElement("canvas");
  const gl =
    canvas.getContext("webgl", { alpha: true, premultipliedAlpha: false }) ||
    canvas.getContext("experimental-webgl", {
      alpha: true,
      premultipliedAlpha: false,
    });
  return Boolean(gl);
}

function initCssFallback() {
  const root = document.documentElement;
  return {
    updateFromConfig: (config) => {
      const blur = clampNumber(config?.background_blur, 0, 40, 10);
      root.style.setProperty("--lg-blur", `${blur}px`);
    },
    destroy: () => {
      root.style.removeProperty("--lg-blur");
    },
  };
}

function initWebGLRenderer() {
  const canvas = document.getElementById("glass-stage");
  const gl = canvas.getContext("webgl", {
    alpha: true,
    antialias: false,
    preserveDrawingBuffer: false,
    premultipliedAlpha: false,
  });

  if (!gl) {
    throw new Error("WebGL context could not be created");
  }

  const glassProgram = createProgram(gl, GLASS_VERTEX_SHADER, GLASS_FRAGMENT_SHADER);

  const quadBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
  gl.bufferData(
    gl.ARRAY_BUFFER,
    new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
    gl.STATIC_DRAW,
  );

  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);

  let image = null;
  let imageUrl = "";
  let config = null;
  let pendingImageUrl = null;
  let targets = [];
  let canvasWidth = 0;
  let canvasHeight = 0;
  let renderHandle = 0;

  const resizeObserver = new ResizeObserver(scheduleRender);
  resizeObserver.observe(document.body);

  window.addEventListener("scroll", scheduleRender, { passive: true });
  window.addEventListener("resize", scheduleRender, { passive: true });

  function refreshTargets() {
    const newTargets = [];
    GLASS_SELECTORS.forEach((selector) => {
      document.querySelectorAll(selector).forEach((element) => {
        if (element.offsetParent === null) return;
        const style = window.getComputedStyle(element);
        if (style.display === "none" || style.visibility === "hidden") return;
        newTargets.push(element);
      });
    });
    // Stable sort by DOM order so later elements draw on top.
    newTargets.sort((a, b) => {
      const position = a.compareDocumentPosition(b);
      return position & Node.DOCUMENT_POSITION_PRECEDING ? 1 : -1;
    });
    targets = newTargets;
    scheduleRender();
  }

  function update(nextImageUrl, nextConfig) {
    config = nextConfig;
    if (!config?.enabled || !nextImageUrl) {
      image = null;
      imageUrl = "";
      clearCanvas();
      return;
    }

    if (nextImageUrl !== imageUrl) {
      imageUrl = nextImageUrl;
      pendingImageUrl = nextImageUrl;
      loadImage(nextImageUrl)
        .then((img) => {
          if (pendingImageUrl !== nextImageUrl) return;
          image = img;
          gl.bindTexture(gl.TEXTURE_2D, texture);
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
          gl.bindTexture(gl.TEXTURE_2D, null);
          scheduleRender();
        })
        .catch((error) => {
          console.warn("[AstrBot调色盘] 壁纸纹理加载失败：", error);
          image = null;
        });
    } else {
      scheduleRender();
    }
  }

  function scheduleRender() {
    if (renderHandle) return;
    renderHandle = requestAnimationFrame(() => {
      renderHandle = 0;
      render();
    });
  }

  function clearCanvas() {
    if (renderHandle) {
      cancelAnimationFrame(renderHandle);
      renderHandle = 0;
    }
    resizeCanvas();
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
  }

  function resizeCanvas() {
    const dpr = getDpr();
    const width = Math.max(1, Math.floor(window.innerWidth * dpr));
    const height = Math.max(1, Math.floor(window.innerHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      canvasWidth = width;
      canvasHeight = height;
      gl.viewport(0, 0, width, height);
    }
  }

  function render() {
    resizeCanvas();
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    if (!image || !config?.enabled) return;

    const bgRect = computeCoverRect(canvasWidth, canvasHeight, image.width, image.height);

    if (!targets.length) return;

    gl.enable(gl.SCISSOR_TEST);
    targets.forEach((element) => {
      drawElementGlass(element, bgRect);
    });
    gl.disable(gl.SCISSOR_TEST);
  }

  function drawElementGlass(element, bgRect) {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    const dpr = getDpr();
    const x = rect.left * dpr;
    const y = canvasHeight - (rect.top + rect.height) * dpr;
    const width = rect.width * dpr;
    const height = rect.height * dpr;

    gl.scissor(
      Math.floor(x),
      Math.floor(y),
      Math.ceil(width),
      Math.ceil(height),
    );

    const style = window.getComputedStyle(element);
    let radius = (parseFloat(style.borderRadius) || 0) * dpr;
    if (style.borderRadius.includes("%")) {
      radius = (Math.min(width, height) * (parseFloat(style.borderRadius) || 0)) / 100;
    }
    radius = Math.min(radius, Math.min(width, height) * 0.5);

    const refractionScale = (4 + clampNumber(config?.background_blur, 0, 40, 10) * 1.5) * dpr;

    gl.useProgram(glassProgram);
    bindQuad(glassProgram, "a_position");
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(gl.getUniformLocation(glassProgram, "u_bgTex"), 0);

    gl.uniform4f(gl.getUniformLocation(glassProgram, "u_bgRect"), bgRect.x, bgRect.y, bgRect.width, bgRect.height);
    gl.uniform4f(gl.getUniformLocation(glassProgram, "u_rect"), x, y, width, height);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_radius"), Math.max(0, radius));
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_refractionScale"), refractionScale);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_noise"), 0.0);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_glowWeight"), 0.18);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_glowBias"), 0.04);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_glowEdge0"), 0.0);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_glowEdge1"), 0.05);
    gl.uniform1f(gl.getUniformLocation(glassProgram, "u_globalAlpha"), 0.72);

    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  function bindQuad(program, attributeName) {
    const location = gl.getAttribLocation(program, attributeName);
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0);
  }

  function destroy() {
    if (renderHandle) cancelAnimationFrame(renderHandle);
    resizeObserver.disconnect();
    window.removeEventListener("scroll", scheduleRender);
    window.removeEventListener("resize", scheduleRender);
    document.body.classList.remove(ACTIVE_CLASS);
  }

  return { refreshTargets, update, destroy };
}

function getDpr() {
  return Math.min(window.devicePixelRatio || 1, 2);
}

function computeCoverRect(canvasWidth, canvasHeight, imageWidth, imageHeight) {
  const canvasAspect = canvasWidth / canvasHeight;
  const imageAspect = imageWidth / imageHeight;
  let width = canvasWidth;
  let height = canvasHeight;
  let x = 0;
  let y = 0;
  if (canvasAspect > imageAspect) {
    height = canvasWidth / imageAspect;
    y = (canvasHeight - height) * 0.5;
  } else {
    width = canvasHeight * imageAspect;
    x = (canvasWidth - width) * 0.5;
  }
  return { x, y, width, height };
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片加载失败"));
    img.src = url;
  });
}

function createProgram(gl, vertexSource, fragmentSource) {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  if (!vertexShader || !fragmentShader) return null;
  const program = gl.createProgram();
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.warn("[AstrBot调色盘] WebGL program link failed:", gl.getProgramInfoLog(program));
    gl.deleteProgram(program);
    return null;
  }
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);
  return program;
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn("[AstrBot调色盘] Shader compile failed:\n", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

function clampNumber(value, minimum, maximum, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(Math.max(number, minimum), maximum);
}

const GLASS_VERTEX_SHADER = `
attribute vec2 a_position;
varying vec2 v_screenUV;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
  v_screenUV = a_position * 0.5 + 0.5;
}
`;

const GLASS_FRAGMENT_SHADER = `
precision mediump float;

varying vec2 v_screenUV;

uniform sampler2D u_bgTex;
uniform vec4 u_bgRect;
uniform vec4 u_rect;
uniform float u_radius;
uniform float u_refractionScale;
uniform float u_noise;
uniform float u_glowWeight;
uniform float u_glowBias;
uniform float u_glowEdge0;
uniform float u_glowEdge1;
uniform float u_globalAlpha;

const float M_E = 2.718281828459045;

float rand(vec2 co) {
  return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453);
}

float f(float x) {
  return 1.0 - 2.3 * pow(5.2 * M_E, -6.9 * x - 0.7);
}

float sdRoundedBox(vec2 p, vec2 b, float r) {
  vec2 d = abs(p) - b + r;
  return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)) - r;
}

float Glow(vec2 uv) {
  vec2 glowUV = uv * 2.0 - 1.0;
  return sin(atan(glowUV.y, glowUV.x) - 0.5);
}

void main() {
  vec2 frag = gl_FragCoord.xy;
  vec2 center = u_rect.xy + u_rect.zw * 0.5;
  vec2 halfSize = u_rect.zw * 0.5;
  vec2 localUV = (frag - u_rect.xy) / u_rect.zw;

  float d = sdRoundedBox(frag - center, halfSize, u_radius);
  float shape = 1.0 - smoothstep(-0.8, 0.8, d);
  if (shape <= 0.0) discard;

  float innerDistance = max(-d, 0.0);
  float shortSide = max(min(halfSize.x, halfSize.y), 1.0);
  float rimWidth = min(18.0, shortSide * 0.32);
  float rim = 1.0 - smoothstep(min(1.0, rimWidth), max(1.0, rimWidth), innerDistance);
  float horizontalMask = smoothstep(0.0, 0.18, localUV.x) * (1.0 - smoothstep(0.82, 1.0, localUV.x));
  float topShine = smoothstep(0.76, 1.0, localUV.y) * horizontalMask;
  float sideShine = max(1.0 - smoothstep(0.0, 0.08, localUV.x), 1.0 - smoothstep(0.0, 0.08, 1.0 - localUV.x));
  float glassMask = clamp(rim * 0.62 + topShine * 0.2 + sideShine * 0.12, 0.0, 0.72) * shape;

  if (glassMask <= 0.002) discard;

  float distNorm = clamp(innerDistance / shortSide, 0.0, 1.0);
  float refraction = pow(f(distNorm), 0.75);

  vec2 dir = normalize((frag - center) + 0.0001);
  vec2 pxOffset = dir * (refraction - 1.0) * u_refractionScale;

  vec2 bgUV = (frag - u_bgRect.xy) / u_bgRect.zw;
  vec2 sampleUV = bgUV + pxOffset / u_bgRect.zw;

  if (sampleUV.x < 0.0 || sampleUV.x > 1.0 || sampleUV.y < 0.0 || sampleUV.y > 1.0) {
    discard;
  }

  vec4 color = texture2D(u_bgTex, sampleUV);

  float grain = (rand(gl_FragCoord.xy * 1e-3) - 0.5) * u_noise;
  color.rgb += vec3(grain);

  float glow = Glow(localUV);
  float glowMask = (1.0 - smoothstep(u_glowEdge0, u_glowEdge1, distNorm)) * glassMask;
  float glowStrength = glow * u_glowWeight * glowMask + 1.0 + u_glowBias;
  color.rgb *= glowStrength;
  color.rgb = mix(color.rgb, vec3(1.0), clamp(glassMask * 0.14 + topShine * 0.12, 0.0, 0.22));

  gl_FragColor = vec4(color.rgb, glassMask * u_globalAlpha);
}
`;
