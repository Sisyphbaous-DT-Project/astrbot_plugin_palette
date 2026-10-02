// 大素材分块上传：同页上传意图、串行切片、真实状态确认与有限等待。
export const CHUNK_THRESHOLD = 16 * 1024 * 1024;
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024;
const MAX_CHUNK_ATTEMPTS = 3;
const BRIDGE_WAIT_TIMEOUT = 75000;
const COMPLETE_POLL_INTERVAL = 1000;
const COMPLETE_WAIT_MS = 180000;
const MAX_CONFIRM_FAILURES = 3;

export function parseUploadProtocol(status) {
  const protocol = status?.upload_protocol;
  if (!protocol || protocol.chunked !== true) return null;
  const chunkSize = Number(protocol.chunk_size);
  if (!Number.isFinite(chunkSize) || chunkSize <= 0) return null;
  const threshold = Number(protocol.threshold);
  return {
    chunkSize,
    threshold: Number.isFinite(threshold) && threshold > 0 ? threshold : CHUNK_THRESHOLD,
  };
}

export function requestIdFor() {
  return `palette-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

export function createUploadIntentStore() {
  const pending = new Map();
  const keyFor = (file, orientation) => JSON.stringify([
    orientation, file.name, file.size, file.lastModified || 0,
  ]);
  return {
    acquire(file, orientation) {
      const key = keyFor(file, orientation);
      if (!pending.has(key)) pending.set(key, { requestId: requestIdFor() });
      return pending.get(key);
    },
    finish(file, orientation, intent) {
      const key = keyFor(file, orientation);
      if (pending.get(key) === intent) pending.delete(key);
    },
  };
}

export function throwIfAborted(signal) {
  if (signal?.aborted) throw new DOMException("上传已取消", "AbortError");
}

function delay(ms, signal) {
  throwIfAborted(signal);
  return new Promise((resolve, reject) => {
    const finish = (error) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      error ? reject(error) : resolve();
    };
    const onAbort = () => finish(new DOMException("上传已取消", "AbortError"));
    const timer = setTimeout(() => finish(), ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

// 本地结束不能中断父页 HTTP；无论取消或超时，都消费已发出 Promise 的拒绝。
function waitBridge(promise, { timeout = BRIDGE_WAIT_TIMEOUT, signal, label } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      error ? reject(error) : resolve(value);
    };
    const onAbort = () => finish(new DOMException("上传已取消", "AbortError"));
    const timer = setTimeout(
      () => finish(new Error(`${label || "上传请求"}等待超时，请检查网络后重试`)), timeout,
    );
    Promise.resolve(promise).then(
      (value) => finish(null, value),
      (error) => finish(error instanceof Error ? error : new Error(String(error))),
    );
    if (signal?.aborted) onAbort();
    else signal?.addEventListener("abort", onAbort, { once: true });
  });
}

// 上传及辅助预览共用有限等待；不改变父页已发 HTTP 请求的生命周期。
export function callBridge(call, options = {}) {
  throwIfAborted(options.signal);
  return waitBridge(call(), options);
}

function unknownResult() {
  const error = new Error("素材入库结果未知，请刷新图库确认；重试将核对原上传，不会新建上传");
  error.name = "UploadResultUnknown";
  return error;
}

function terminalResult(receipt, session) {
  if (receipt?.state) session.state = receipt.state;
  if (receipt?.state === "committed" && receipt.result) return receipt.result;
  if (receipt?.state === "failed" || receipt?.state === "cancelled") {
    const error = receipt.state === "cancelled"
      ? new DOMException("服务器已取消上传", "AbortError")
      : new Error(receipt.error || "素材入库失败，请重试");
    error.serverCancelled = receipt.state === "cancelled";
    error.uploadTerminal = true;
    throw error;
  }
  return null;
}

async function querySessionStatus(bridge, uploadId, signal, timeout) {
  return callBridge(() => bridge.apiGet(`uploads/${uploadId}/status`), {
    signal, timeout: timeout || BRIDGE_WAIT_TIMEOUT, label: "上传状态查询",
  });
}

// 只在明确 receiving 时发送 complete；processing 或响应丢失均优先查状态。
async function confirmCompletion(bridge, session, options, initial) {
  const { signal, bridgeTimeout, onConfirming, allowComplete = true } = options;
  const deadline = session.confirmDeadline || (Date.now() + COMPLETE_WAIT_MS);
  session.confirmDeadline = deadline;
  let receipt = initial;
  let failures = 0;
  onConfirming?.();
  for (;;) {
    throwIfAborted(signal);
    const result = terminalResult(receipt, session);
    if (result) return result;
    const remaining = deadline - Date.now();
    if (remaining <= 0) throw unknownResult();
    const timeout = Math.min(bridgeTimeout || BRIDGE_WAIT_TIMEOUT, remaining);
    const sendComplete = receipt?.state === "receiving";
    if (sendComplete && !allowComplete) throw unknownResult();
    try {
      receipt = sendComplete
        ? await callBridge(() => bridge.apiPost(`uploads/${session.uploadId}/complete`, {}), {
          signal, timeout, label: "素材入库",
        })
        : await querySessionStatus(bridge, session.uploadId, signal, timeout);
      failures = 0;
    } catch (error) {
      if (error.name === "AbortError") throw error;
      receipt = null;
      failures += 1;
      if (failures >= MAX_CONFIRM_FAILURES) throw unknownResult();
    }
    const confirmed = terminalResult(receipt, session);
    if (confirmed) return confirmed;
    const afterRequest = deadline - Date.now();
    if (afterRequest <= 0) throw unknownResult();
    // complete 响应丢失立即核对；正常 processing 按间隔轮询。
    if (receipt) await delay(Math.min(COMPLETE_POLL_INTERVAL, afterRequest), signal);
  }
}

// 尽力取消并返回真实回执；网络失败不能据此宣称服务器已经停止。
export async function cancelChunkedUpload(bridge, uploadId, timeout = BRIDGE_WAIT_TIMEOUT) {
  if (!uploadId) return null;
  try {
    return await callBridge(() => bridge.apiPost(`uploads/${uploadId}/cancel`, {}), {
      timeout, label: "取消上传",
    });
  } catch (_) { return null; }
}

export function requestChunkedCancellation(bridge, session, timeout) {
  if (!session?.uploadId) return Promise.resolve(null);
  if (!session.cancelPromise) {
    session.confirmDeadline ||= Date.now() + COMPLETE_WAIT_MS;
    const remaining = Math.max(1, session.confirmDeadline - Date.now());
    session.cancelPromise = cancelChunkedUpload(
      bridge, session.uploadId, Math.min(timeout || BRIDGE_WAIT_TIMEOUT, remaining),
    );
  }
  return session.cancelPromise;
}

export async function uploadChunked(bridge, file, orientation, options) {
  const { protocol, requestId, signal, onProgress, bridgeTimeout } = options;
  const session = options.session || {};
  // 同一次未知结果的重试保留身份，但允许再次请求取消。
  session.cancelPromise = null;
  session.confirmDeadline = null;
  const waitOptions = { signal, timeout: bridgeTimeout || BRIDGE_WAIT_TIMEOUT };
  try {
    throwIfAborted(signal);
    let receipt;
    if (session.uploadId) {
      session.confirmDeadline = Date.now() + COMPLETE_WAIT_MS;
      try {
        receipt = await querySessionStatus(bridge, session.uploadId, signal, bridgeTimeout);
      } catch (error) {
        if (error.name === "AbortError") throw error;
        throw unknownResult();
      }
    } else {
      session.started = true;
      receipt = await callBridge(() => bridge.apiPost("uploads/init", {
        client_request_id: requestId,
        orientation,
        total_bytes: file.size,
        filename: (file.name || "upload.bin").slice(0, 200),
      }), { ...waitOptions, label: "上传会话创建" });
      session.uploadId = String(receipt?.upload_id || "");
      if (!session.uploadId) throw new Error("上传会话创建失败，请刷新后重试");
    }
    const result = terminalResult(receipt, session);
    if (result) return result;
    if (receipt.state === "processing" || receipt.state === "committed") {
      return await confirmCompletion(bridge, session, options, receipt);
    }
    session.confirmDeadline = null;
    const negotiated = Number(receipt.chunk_size) || session.chunkSize || protocol?.chunkSize || DEFAULT_CHUNK_SIZE;
    session.chunkSize = negotiated;
    const totalChunks = Math.max(1, Math.ceil(file.size / negotiated));
    let nextIndex = Math.min(Number(receipt.next_index) || 0, totalChunks);
    let received = Number(receipt.received_bytes) || 0;
    while (nextIndex < totalChunks) {
      throwIfAborted(signal);
      const start = nextIndex * negotiated;
      const slice = file.slice(start, Math.min(start + negotiated, file.size));
      let confirmed = false;
      for (let attempt = 1; attempt <= MAX_CHUNK_ATTEMPTS && !confirmed; attempt += 1) {
        try {
          receipt = await callBridge(() => bridge.upload(
            `uploads/${session.uploadId}/chunk/${nextIndex}`,
            new File([slice], file.name || "chunk.bin", { type: "application/octet-stream" }),
          ), { ...waitOptions, label: "分块上传" });
          nextIndex = Number(receipt.next_index);
          received = Number(receipt.received_bytes);
          confirmed = true;
        } catch (error) {
          if (error.name === "AbortError") throw error;
          let status = null;
          try {
            status = await querySessionStatus(bridge, session.uploadId, signal, bridgeTimeout);
          } catch (statusError) {
            if (statusError.name === "AbortError") throw statusError;
          }
          const recovered = terminalResult(status, session);
          if (recovered) return recovered;
          if (status?.state === "processing") {
            return await confirmCompletion(bridge, session, options, status);
          }
          if (Number(status?.next_index) > nextIndex) {
            nextIndex = Number(status.next_index);
            received = Number(status.received_bytes) || received;
            confirmed = true;
            break;
          }
          if (attempt >= MAX_CHUNK_ATTEMPTS) throw new Error(`分块上传失败：${error?.message || "网络错误"}`);
          await delay(400 * attempt, signal);
        }
      }
      onProgress?.({ receivedBytes: Math.min(received, file.size), totalBytes: file.size, nextIndex, totalChunks });
    }
    return await confirmCompletion(bridge, session, options, { state: "receiving" });
  } catch (error) {
    if (error.name !== "AbortError" || error.serverCancelled || !session.uploadId) throw error;
    const receipt = await requestChunkedCancellation(bridge, session, bridgeTimeout);
    const result = terminalResult(receipt, session);
    if (result) return result;
    // 已开始入库不能强行回滚；停止后续文件，单独确认当项的最终结果。
    return await confirmCompletion(bridge, session, {
      ...options, signal: undefined, allowComplete: false,
    }, receipt);
  }
}

export async function uploadPrepared(bridge, file, orientation, options = {}) {
  const { protocol, signal, session, bridgeTimeout } = options;
  throwIfAborted(signal);
  const threshold = protocol?.threshold || CHUNK_THRESHOLD;
  if (file.size < threshold) {
    if (session) session.started = true;
    return await callBridge(() => bridge.upload(`upload-background/${orientation}`, file), {
      signal, timeout: bridgeTimeout || BRIDGE_WAIT_TIMEOUT, label: "素材上传",
    });
  }
  if (!protocol) throw new Error("素材超过单次上传限制，且当前插件后端不支持分块上传；请刷新页面或升级插件后重试");
  return await uploadChunked(bridge, file, orientation, options);
}

export async function configForUploadResult(bridge, result) {
  return result.config || await callBridge(() => bridge.apiGet("config"), {
    label: "最新图库读取",
  });
}
