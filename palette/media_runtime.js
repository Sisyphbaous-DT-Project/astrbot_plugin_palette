/* AstrBot调色盘 动态背景运行时辅助：视频元素生命周期与静态兜底。
 *
 * 该文件由 palette/injector.py 读取并内嵌进 Dashboard 注入脚本，
 * 同时作为 CommonJS 模块被 node 行为测试直接加载；不要在浏览器
 * 全局注入除 AstrBotPaletteMedia 以外的标识符。
 */
(function (root, factory) {
  var api = factory();
  root.AstrBotPaletteMedia = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  // 首帧等待上限：本地 blob 解码通常很快，超时只兜底隐藏页面等异常。
  var FIRST_FRAME_TIMEOUT_MS = 10000;

  function videoObjectFit(backgroundFit) {
    // background_fit → object-fit 映射：stretch 对应 fill，auto 对应 none。
    if (backgroundFit === "stretch") {
      return "fill";
    }
    if (backgroundFit === "auto") {
      return "none";
    }
    return ["cover", "contain"].indexOf(backgroundFit) === -1
      ? "cover"
      : backgroundFit;
  }

  function prefersReducedMotion(root) {
    // 系统“减少动态效果”优先于插件的动态背景开关。
    try {
      var target =
        root || (typeof window !== "undefined" ? window : undefined);
      return Boolean(
        target &&
          target.matchMedia &&
          target.matchMedia("(prefers-reduced-motion: reduce)").matches,
      );
    } catch (_) {
      return false;
    }
  }

  function createLayerVideo(doc) {
    // 背景视频永远是静音、循环、内联的装饰元素：不响应点击、无控件。
    var video = doc.createElement("video");
    video.className = "astrbot-palette-background-video";
    video.muted = true;
    video.defaultMuted = true;
    video.loop = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    video.setAttribute("webkit-playsinline", "");
    video.setAttribute("aria-hidden", "true");
    video.setAttribute("tabindex", "-1");
    video.preload = "auto";
    video.disableRemotePlayback = true;
    return video;
  }

  function waitForFirstFrame(video, timeoutMs, signal) {
    // 视频的首帧就绪不能照搬图片的 decode()：HAVE_CURRENT_DATA
    // （loadeddata）表示首帧可呈现，支持 requestVideoFrameCallback 时
    // 以真实呈现为准；超时兜底避免隐藏页面悬挂异步流程。
    return new Promise(function (resolve, reject) {
      if (signal && signal.aborted) {
        reject(new DOMException("视频准备已取消。", "AbortError"));
        return;
      }
      if (video.readyState >= 2) {
        resolve();
        return;
      }
      if (video.error) {
        reject(new Error("视频加载失败。"));
        return;
      }
      var settled = false;
      var frameCallback = null;
      var finish = function (ok, error) {
        if (settled) {
          return;
        }
        settled = true;
        video.removeEventListener("loadeddata", onReady);
        video.removeEventListener("error", onError);
        if (signal) {
          signal.removeEventListener("abort", onAbort);
        }
        clearTimeout(timer);
        if (frameCallback !== null && video.cancelVideoFrameCallback) {
          video.cancelVideoFrameCallback(frameCallback);
        }
        if (ok) {
          resolve();
        } else {
          reject(error || new Error("视频加载失败。"));
        }
      };
      var onReady = function () {
        finish(true);
      };
      var onError = function () {
        finish(false, new Error("视频加载失败。"));
      };
      var onAbort = function () {
        finish(false, new DOMException("视频准备已取消。", "AbortError"));
      };
      var timer = setTimeout(function () {
        finish(false, new Error("视频首帧等待超时。"));
      }, typeof timeoutMs === "number" ? timeoutMs : FIRST_FRAME_TIMEOUT_MS);
      video.addEventListener("loadeddata", onReady);
      video.addEventListener("error", onError);
      if (signal) {
        signal.addEventListener("abort", onAbort, { once: true });
      }
      if (typeof video.requestVideoFrameCallback === "function") {
        try {
          frameCallback = video.requestVideoFrameCallback(function () {
            finish(true);
          });
        } catch (_) {
          // 回调注册失败时仍有 loadeddata 与超时兜底。
        }
      }
    });
  }

  function playVideo(video) {
    // true 为已播放，false 为失败，null 为主动暂停打断。
    // AbortError 不代表素材不可用，不能据此永久关闭播放意图。
    if (!video.paused) {
      return Promise.resolve(true);
    }
    try {
      var result = video.play();
      if (result && typeof result.then === "function") {
        return Promise.race([result.then(
          function () {
            return true;
          },
          function (error) {
            return error && error.name === "AbortError" ? null : false;
          },
        ), new Promise(function (resolve) {
          var timer = setTimeout(function () { resolve(false); }, 3000);
          result.then(function () { clearTimeout(timer); }, function () { clearTimeout(timer); });
        })]);
      }
      return Promise.resolve(true);
    } catch (error) {
      return Promise.resolve(error && error.name === "AbortError" ? null : false);
    }
  }

  function pauseVideo(video) {
    try {
      video.pause();
    } catch (_) {
      // 已销毁或不支持时静默。
    }
  }

  function destroyLayerVideo(video) {
    // 释放解码资源：清空 src 并触发 load，再从图层移除。
    if (!video) {
      return;
    }
    pauseVideo(video);
    if (video.__paletteErrorHandler) {
      video.removeEventListener("error", video.__paletteErrorHandler);
      video.__paletteErrorHandler = null;
    }
    try {
      video.removeAttribute("src");
    } catch (_) {
      // 忽略。
    }
    try {
      video.load();
    } catch (_) {
      // 忽略。
    }
    if (video.parentNode) {
      video.parentNode.removeChild(video);
    }
  }

  function isPaletteSettingsMessage(event, root) {
    // 核心设置页 iframe 是 opaque origin（"null"），必须同时核对
    // contentWindow 和插件页面路径，不能放行所有 null 来源。
    if (!root.location || !event.source ||
        (event.origin !== root.location.origin && event.origin !== "null")) {
      return false;
    }
    var frames = root.document.querySelectorAll("iframe");
    for (var index = 0; index < frames.length; index += 1) {
      var frame = frames[index];
      if (frame.contentWindow !== event.source) {
        continue;
      }
      try {
        var source = new root.URL(frame.getAttribute("src"), root.location.href);
        return source.origin === root.location.origin &&
          source.pathname.indexOf("/api/plugin/page/content/astrbot_plugin_palette/settings/") === 0;
      } catch (_) {
        return false;
      }
    }
    return false;
  }

  function attachPreviewBridge(root, getToken) {
    // opaque iframe 不能读 localStorage：主页面只为经过来源校验的
    // 调色盘设置页下载限定素材，并传输 ArrayBuffer，不传递登录令牌。
    var pending = new Map();
    var onMessage = async function (event) {
      var data = event.data;
      if (!data || !isPaletteSettingsMessage(event, root)) {
        return;
      }
      var previous = pending.get(event.source);
      if (data.type === "astrbot-palette:media-cancel") {
        if (previous && previous.id === data.requestId) {
          previous.controller.abort();
        }
        return;
      }
      if (data.type !== "astrbot-palette:media-request" ||
          typeof data.requestId !== "string" || data.requestId.length > 120 ||
          typeof data.filename !== "string" ||
          !/^[a-zA-Z0-9_-]+\.(?:jpe?g|png|webp|gif|svg|mp4|webm)$/i.test(data.filename)) {
        return;
      }
      if (previous) {
        previous.controller.abort();
      }
      var controller = new root.AbortController();
      var entry = { id: data.requestId, controller: controller };
      pending.set(event.source, entry);
      var timer = root.setTimeout(function () { controller.abort(); }, 60000);
      try {
        var prefix = "/api/v1/plugins/extensions/astrbot_plugin_palette/";
        var path = data.cover === true
          ? prefix + "background-cover?filename=" + encodeURIComponent(data.filename)
          : prefix + "backgrounds/" + encodeURIComponent(data.filename);
        var limit = !data.cover && /\.(mp4|webm)$/i.test(data.filename)
          ? 100 * 1024 * 1024 : 10 * 1024 * 1024;
        var token = getToken();
        var response = await root.fetch(path, {
          signal: controller.signal,
          credentials: "same-origin",
          headers: token ? { Authorization: "Bearer " + token } : {},
        });
        if (!response.ok) {
          throw new Error("素材读取失败（HTTP " + response.status + "）");
        }
        if ((Number(response.headers.get("Content-Length")) || 0) > limit) {
          throw new Error("素材超过预览大小限制。");
        }
        var buffer = await response.arrayBuffer();
        if (buffer.byteLength > limit) {
          throw new Error("素材超过预览大小限制。");
        }
        if (pending.get(event.source) !== entry || controller.signal.aborted ||
            !isPaletteSettingsMessage(event, root)) {
          return;
        }
        var type = response.headers.get("Content-Type") || "application/octet-stream";
        // 只向已核实的 source 回传；opaque iframe 要求 targetOrigin="*"。
        event.source.postMessage({
          type: "astrbot-palette:media-response",
          requestId: data.requestId, success: true, contentType: type, buffer: buffer,
        }, "*", [buffer]);
      } catch (error) {
        if (pending.get(event.source) === entry && isPaletteSettingsMessage(event, root)) {
          event.source.postMessage({
            type: "astrbot-palette:media-response",
            requestId: data.requestId, success: false,
            message: error.name === "AbortError" ? "素材读取已取消或超时。" : error.message,
          }, "*");
        }
      } finally {
        root.clearTimeout(timer);
        if (pending.get(event.source) === entry) {
          pending.delete(event.source);
        }
      }
    };
    var cancelAll = function () {
      pending.forEach(function (entry) { entry.controller.abort(); });
      pending.clear();
    };
    root.addEventListener("message", onMessage);
    root.addEventListener("pagehide", cancelAll);
    return {
      destroy: function () {
        cancelAll();
        root.removeEventListener("message", onMessage);
        root.removeEventListener("pagehide", cancelAll);
      },
    };
  }

  return {
    FIRST_FRAME_TIMEOUT_MS: FIRST_FRAME_TIMEOUT_MS,
    createLayerVideo: createLayerVideo,
    destroyLayerVideo: destroyLayerVideo,
    pauseVideo: pauseVideo,
    playVideo: playVideo,
    prefersReducedMotion: prefersReducedMotion,
    videoObjectFit: videoObjectFit,
    waitForFirstFrame: waitForFirstFrame,
    isPaletteSettingsMessage: isPaletteSettingsMessage,
    attachPreviewBridge: attachPreviewBridge,
  };
});
