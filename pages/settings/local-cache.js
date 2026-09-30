// 设置页是沙箱 iframe，本机缓存由主页面管理，沿用严格来源校验的消息桥。
export function initLocalCache(status, clearButton, report) {
  let requestNumber = 0;
  let pending = null;
  function request(action) {
    if (pending) return pending.promise;
    const origin = new URL(window.location.href).origin;
    const requestId = `palette-cache-${Date.now()}-${++requestNumber}`;
    let finish;
    const promise = new Promise((resolve, reject) => {
      const onMessage = (event) => {
        if (event.source !== window.parent || event.origin !== origin ||
            event.data?.type !== "astrbot-palette:cache-response" ||
            event.data.requestId !== requestId) return;
        finish(null, event.data.status);
      };
      const timer = setTimeout(() => finish(new Error("本机缓存状态读取失败，请刷新 WebUI 后重试")), 12000);
      finish = (error, value) => {
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        pending = null;
        error ? reject(error) : resolve(value);
      };
      window.addEventListener("message", onMessage);
      window.parent.postMessage({ type: "astrbot-palette:cache-request", requestId, action }, origin);
    });
    pending = { promise, cancel: () => finish(new Error("缓存操作已取消")) };
    return promise;
  }
  function render(info) {
    status.textContent = info.available
      ? `普通缓存：${(info.budgetBytes / 1024 / 1024).toFixed(1)} / ${info.maxBytes / 1024 / 1024}MiB · 大素材：${(info.largeBytes / 1024 / 1024).toFixed(1)}MiB（${info.largeCount} 项，单独保留）`
      : "本机缓存不可用，仍可正常下载播放";
    clearButton.disabled = !info.available;
  }
  async function refresh() {
    try { render(await request("stats")); }
    catch (_) { status.textContent = "本机缓存状态暂不可用，刷新 WebUI 后重试"; }
  }
  clearButton.addEventListener("click", async () => {
    if (pending) return;
    clearButton.disabled = true;
    try {
      const info = await request("clear");
      render(info);
      report(info.cleared ? "已清理本机缓存，当前播放和服务器图库保留" : "本机缓存清理失败，请重试",
        info.cleared ? "success" : "danger");
    } catch (error) { clearButton.disabled = false; report(error.message, "danger"); }
  });
  window.addEventListener("pagehide", () => pending?.cancel());
  return { refresh };
}
