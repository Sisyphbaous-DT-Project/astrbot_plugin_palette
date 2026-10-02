"""大素材分块上传：会话、块写入、完成、取消、回执与过期清理。

AstrBot 4.29 起插件扩展路由的单个 HTTP 请求受核心 128MiB 总限制，
封面、包头和 multipart 包装都计入。为保留大素材上传能力，设置页把
素材包切成固定块长的小包依次上传，服务端按会话顺序落盘，收齐后复用
`palette.media.save_background_upload` 的解析/校验/封面链路和主入口的
图库合并逻辑入库，不另建第二套图库规则。

可靠性边界：
- 客户端只能提供显示名和 client_request_id；存储路径、素材 ID 均由
  服务器生成，会话绑定已鉴权用户名，防止会话混用。
- 配置保存成功是不可回滚边界：之后的回执写盘、响应构造或客户端离开
  出错，都不能删除正式素材；重复 complete/status 返回同一素材身份。
- 服务重启使未完成的传输失效（receiving 直接清理）；已写入配置但
  回执未落的 committing 会话在启动时按正式图库引用核对补写回执，
  未提交的候选残留按服务器生成的素材 ID 精确清理，不扫描正式图库。
- 过期清理只处理上传管理器自己的会话目录，不碰正式素材和其它目录。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .file_tasks import run_file_task

# 协商固定块长：连同 multipart 包装远低于核心 128MiB 请求限制。
CHUNK_SIZE = 8 * 1024 * 1024
# 前端按完整上传包大小选择通道：小于该值继续走旧的单次上传接口。
CHUNKED_UPLOAD_THRESHOLD = 16 * 1024 * 1024
MAX_DISPLAY_NAME_LENGTH = 200
MAX_REQUEST_ID_LENGTH = 128
# receiving 闲置 30 分钟过期；committed 回执保留 24 小时供重复查询去重。
RECEIVING_IDLE_TTL_SECONDS = 30 * 60
COMMITTED_RECEIPT_TTL_SECONDS = 24 * 60 * 60
MAX_ACTIVE_SESSIONS = 8
MAX_ACTIVE_SESSIONS_PER_USER = 2

_UPLOAD_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_MATERIAL_ID_PATTERN = re.compile(r"[0-9a-f]{32}")

STATE_RECEIVING = "receiving"
STATE_PROCESSING = "processing"
STATE_COMMITTED = "committed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class UploadError(ValueError):
    """分块上传的可预期失败，消息直接展示给用户。"""


@dataclass
class UploadHooks:
    """与主插件的接入口；素材与图库规则仍由 main.py / media.py 实现。"""

    # 从临时包流式解析/校验/生成封面，返回正式素材文件名；失败自行清理。
    save_material: Callable[[Any, str], Awaitable[str]]
    # 持有配置锁把已备素材并入最新图库并保存；抛错时必须尚未保存。
    commit_material: Callable[[str, str], Awaitable[None]]
    # 用当前最新配置构造成功回执；允许失败，不回填过期配置快照。
    build_result: Callable[[str, str], dict[str, Any]]
    # 按服务器生成的素材 ID 精确清理未提交的候选原素材/封面/缩略图。
    cleanup_candidate: Callable[[str], None]
    # 启动恢复：素材 ID 已被任一正式图库引用且原素材存在时返回文件名。
    find_committed_material: Callable[[str], str]


@dataclass
class UploadSession:
    upload_id: str
    username: str
    client_request_id: str
    orientation: str
    total_bytes: int
    display_name: str
    material_id: str
    chunk_size: int
    directory: Path
    state: str = STATE_RECEIVING
    saved_filename: str = ""
    received_bytes: int = 0
    next_index: int = 0
    chunk_digests: list[str] = field(default_factory=list)
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task | None = None

    @property
    def payload_path(self) -> Path:
        return self.directory / "payload.bin"

    @property
    def meta_path(self) -> Path:
        return self.directory / "session.json"


class FileUploadReader:
    """把已落盘的临时包包装成 save_background_upload 需要的异步读取接口。

    保持逐段读取（现有保存链路按 1MiB 拉取），不整包读入内存。
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None
        self._offset = 0

    def _ensure_handle(self):
        if self._handle is None:
            self._handle = self._path.open("rb")
        return self._handle

    async def seek(self, offset: int) -> None:
        self._offset = offset
        handle = self._handle
        if handle is not None:
            await run_file_task(handle.seek, offset)

    async def read(self, size: int = -1) -> bytes:
        def _read() -> bytes:
            handle = self._ensure_handle()
            handle.seek(self._offset)
            data = handle.read(size)
            self._offset += len(data)
            return data

        return await run_file_task(_read)

    async def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            with suppress(OSError):
                await run_file_task(handle.close)


class UploadManager:
    """分块上传会话管理器；路由层只做参数转发。"""

    def __init__(
        self,
        paths,
        hooks: UploadHooks,
        *,
        chunk_size: int = CHUNK_SIZE,
    ) -> None:
        self._paths = paths
        self._hooks = hooks
        self._chunk_size = chunk_size
        self._sessions: dict[str, UploadSession] = {}
        self._registry_lock = asyncio.Lock()
        self._last_sweep = 0.0

    def capability(self) -> dict[str, Any]:
        return {
            "chunked": True,
            "chunk_size": self._chunk_size,
            "threshold": CHUNKED_UPLOAD_THRESHOLD,
        }

    # ------------------------------------------------------------------
    # 会话创建

    async def init_session(self, username: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise UploadError("上传请求格式不正确。")
        client_request_id = str(payload.get("client_request_id") or "").strip()
        if not client_request_id or len(client_request_id) > MAX_REQUEST_ID_LENGTH:
            raise UploadError("上传请求标识不正确。")
        orientation = str(payload.get("orientation") or "").strip().lower()
        if orientation not in {"landscape", "portrait"}:
            raise UploadError("上传方向不正确。")
        try:
            total_bytes = int(payload.get("total_bytes"))
        except (TypeError, ValueError):
            raise UploadError("上传大小不正确。") from None
        if isinstance(payload.get("total_bytes"), bool) or total_bytes <= 0:
            raise UploadError("上传大小不正确。")
        display_name = Path(
            str(payload.get("filename") or "upload.bin")
        ).name.strip()[:MAX_DISPLAY_NAME_LENGTH]
        if not display_name:
            display_name = "upload.bin"

        await self._sweep_expired()
        async with self._registry_lock:
            existing = self._find_by_request_id(username, client_request_id)
            if existing is not None:
                if existing.state in {STATE_FAILED, STATE_CANCELLED}:
                    # 已终结的失败会话不占 request_id，用户显式重试时允许重建。
                    self._remove_session(existing)
                else:
                    if (
                        existing.orientation != orientation
                        or existing.total_bytes != total_bytes
                        or existing.display_name != display_name
                    ):
                        raise UploadError(
                            "同一上传请求的参数不一致，请刷新后重新选择素材。"
                        )
                    return self._session_receipt(existing)

            active = [
                session
                for session in self._sessions.values()
                if session.state in {STATE_RECEIVING, STATE_PROCESSING}
            ]
            if len(active) >= MAX_ACTIVE_SESSIONS or sum(
                session.username == username for session in active
            ) >= MAX_ACTIVE_SESSIONS_PER_USER:
                raise UploadError("同时进行的上传过多，请等待当前上传完成。")

            now = time.time()
            session = UploadSession(
                upload_id=secrets.token_hex(16),
                username=username,
                client_request_id=client_request_id,
                orientation=orientation,
                total_bytes=total_bytes,
                display_name=display_name,
                material_id=secrets.token_hex(16),
                chunk_size=self._chunk_size,
                directory=self._paths.upload_dir / secrets.token_hex(16),
                created_at=now,
                updated_at=now,
            )
            try:
                session.directory.mkdir(parents=True, exist_ok=False)
                session.payload_path.touch(exist_ok=False)
            except OSError as exc:
                self._remove_directory(session.directory)
                raise UploadError("上传目录创建失败，请检查磁盘空间。") from exc
            self._sessions[session.upload_id] = session
            try:
                self._persist_meta(session)
            except OSError as exc:
                self._remove_session(session)
                raise UploadError("上传会话记录失败，请检查磁盘空间。") from exc
            return self._session_receipt(session)

    def _find_by_request_id(
        self, username: str, client_request_id: str
    ) -> UploadSession | None:
        for session in self._sessions.values():
            if (
                session.username == username
                and session.client_request_id == client_request_id
            ):
                return session
        return None

    def _session_receipt(self, session: UploadSession) -> dict[str, Any]:
        return {
            "upload_id": session.upload_id,
            "chunk_size": session.chunk_size,
            "next_index": session.next_index,
            "received_bytes": session.received_bytes,
            "state": session.state,
            "expires_in_seconds": RECEIVING_IDLE_TTL_SECONDS,
            "result": self._committed_result(session),
        }

    # ------------------------------------------------------------------
    # 块写入

    async def append_chunk(
        self, username: str, upload_id: str, index_value: Any, upload_file
    ) -> dict[str, Any]:
        session = self._get_session(username, upload_id)
        index = self._parse_index(index_value)
        async with session.lock:
            if session.state != STATE_RECEIVING:
                if 0 <= index < session.next_index:
                    # 已完成/取消后迟到的重复块只回确认，不再写入。
                    return self._chunk_receipt(session)
                raise UploadError(self._state_message(session))
            total_chunks = self._total_chunks(session)
            if index >= total_chunks:
                raise UploadError("分块序号超出范围。")
            expected = self._chunk_length(session, index)
            if index < session.next_index:
                # 重复的旧块：核对长度和摘要，相同返回原确认，不同按冲突拒绝。
                digest, length = await self._hash_upload(upload_file, expected)
                if length != expected or digest != session.chunk_digests[index]:
                    raise UploadError("重复分块与已确认内容不一致，请重新上传。")
                return self._chunk_receipt(session)
            if index > session.next_index:
                raise UploadError("分块顺序不正确，请按确认位置继续。")

            confirmed = session.received_bytes
            hasher = hashlib.sha256()
            written = 0
            try:
                with session.payload_path.open("r+b") as output:
                    output.seek(confirmed)
                    while True:
                        data = await upload_file.read(1024 * 1024)
                        if not data:
                            break
                        if written + len(data) > expected:
                            raise UploadError("分块长度与协商不一致。")
                        hasher.update(data)
                        await self._write_chunk(output, data)
                        written += len(data)
                    if written == 0:
                        raise UploadError("分块内容为空。")
                    if written != expected:
                        raise UploadError("分块长度与协商不一致。")
                    await self._write_chunk(output, b"", flush=True)
            except BaseException:
                # 截断、写盘失败或请求取消：回滚到已确认长度，不推进 next_index。
                await self._rollback_payload(session, confirmed)
                raise
            session.received_bytes = confirmed + written
            session.next_index = index + 1
            session.chunk_digests.append(hasher.hexdigest())
            session.updated_at = time.time()
            try:
                self._persist_meta(session)
            except OSError as exc:
                await self._rollback_payload(session, confirmed)
                session.received_bytes = confirmed
                session.next_index = index
                session.chunk_digests.pop()
                raise UploadError("上传进度记录失败，请检查磁盘空间。") from exc
            return self._chunk_receipt(session)

    async def _write_chunk(self, output, data: bytes, flush=False):
        """写盘转线程执行；请求取消必须等线程真正结束后再回滚。"""

        def _write() -> None:
            if data:
                output.write(data)
            if flush:
                output.flush()

        await run_file_task(_write)

    async def _rollback_payload(self, session: UploadSession, confirmed: int) -> None:
        def _truncate() -> None:
            with session.payload_path.open("r+b") as output:
                output.truncate(confirmed)

        with suppress(OSError):
            await run_file_task(_truncate)

    async def _hash_upload(self, upload_file, limit: int) -> tuple[str, int]:
        await upload_file.seek(0)
        hasher = hashlib.sha256()
        length = 0
        while True:
            data = await upload_file.read(1024 * 1024)
            if not data:
                break
            length += len(data)
            if length > limit:
                break
            hasher.update(data)
        return hasher.hexdigest(), length

    def _chunk_receipt(self, session: UploadSession) -> dict[str, Any]:
        return {
            "upload_id": session.upload_id,
            "received_bytes": session.received_bytes,
            "next_index": session.next_index,
            "state": session.state,
        }

    # ------------------------------------------------------------------
    # 状态、完成、取消

    async def get_status(self, username: str, upload_id: str) -> dict[str, Any]:
        session = self._get_session(username, upload_id)
        # 状态查询只读快照，不等待 processing 的长任务，不重复入库。
        return {
            "upload_id": session.upload_id,
            "state": session.state,
            "saved_filename": session.saved_filename,
            "received_bytes": session.received_bytes,
            "next_index": session.next_index,
            "total_bytes": session.total_bytes,
            "error": session.error,
            "result": self._committed_result(session),
        }

    def _committed_result(self, session: UploadSession) -> dict[str, Any] | None:
        """只保留成功素材身份，每次查询都读取当前最新配置。"""

        if session.state == STATE_COMMITTED and session.saved_filename:
            try:
                return self._hooks.build_result(
                    session.saved_filename, session.orientation
                )
            except Exception:
                # 临时响应失败不改变提交结果；后续查询仍重新尝试构造配置。
                return {
                    "message": "背景素材已加入图库。",
                    "background_image": session.saved_filename,
                    "orientation": session.orientation,
                }
        return None

    async def complete(self, username: str, upload_id: str) -> dict[str, Any]:
        session = self._get_session(username, upload_id)
        async with session.lock:
            if session.state == STATE_COMMITTED:
                return {
                    "state": STATE_COMMITTED,
                    "result": self._committed_result(session),
                }
            if session.state == STATE_PROCESSING:
                return {"state": STATE_PROCESSING}
            if session.state != STATE_RECEIVING:
                raise UploadError(self._state_message(session))
            if session.received_bytes != session.total_bytes or session.next_index != (
                self._total_chunks(session)
            ):
                raise UploadError("还有未确认的分块，请继续上传。")
            # 先落 committing 回执再建任务：服务重启后可按素材 ID 核对结果。
            session.state = STATE_PROCESSING
            session.updated_at = time.time()
            try:
                self._persist_meta(session)
            except OSError as exc:
                session.state = STATE_RECEIVING
                raise UploadError("上传进度记录失败，请检查磁盘空间。") from exc
            session.task = asyncio.create_task(
                self._run_commit(session),
                name=f"palette-upload-{session.upload_id}",
            )
            return {"state": STATE_PROCESSING}

    async def cancel(self, username: str, upload_id: str) -> dict[str, Any]:
        session = self._get_session(username, upload_id)
        async with session.lock:
            if session.state == STATE_RECEIVING:
                session.state = STATE_CANCELLED
                session.updated_at = time.time()
                self._remove_session(session)
                return {"state": STATE_CANCELLED}
            # processing/committed 已越过可取消边界，返回真实状态；
            # 重复 cancel 绝不删除正式素材。
            return {
                "state": session.state,
                "message": "素材正在入库或已完成，请在图库中确认结果。",
                "result": self._committed_result(session),
            }

    async def _run_commit(self, session: UploadSession) -> None:
        reader = FileUploadReader(session.payload_path)
        saved_filename = ""
        committed = False
        try:
            saved_filename = await self._hooks.save_material(
                reader, session.material_id
            )
            await self._hooks.commit_material(saved_filename, session.orientation)
            committed = True
        except BaseException as exc:
            session.error = str(exc) or "素材入库失败。"
            session.state = STATE_FAILED
            session.updated_at = time.time()
            if saved_filename and not committed:
                # 入库未越界：候选只属于本会话，按素材 ID 精确清理。
                with suppress(Exception):
                    self._hooks.cleanup_candidate(session.material_id)
            with suppress(OSError):
                session.payload_path.unlink()
            with suppress(OSError):
                self._persist_meta(session)
            if isinstance(exc, asyncio.CancelledError):
                raise
            return
        finally:
            await reader.close()

        # 配置已保存：之后任何失败都不能再删除正式素材。
        session.state = STATE_COMMITTED
        session.saved_filename = saved_filename
        session.updated_at = time.time()
        with suppress(OSError):
            session.payload_path.unlink()
        with suppress(OSError):
            self._persist_meta(session)

    # ------------------------------------------------------------------
    # 过期清理与启动恢复

    async def _sweep_expired(self) -> None:
        now = time.time()
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        for session in list(self._sessions.values()):
            if session.lock.locked():
                # 在途写线程仍持有会话锁，清理不与其竞态。
                continue
            if session.state == STATE_PROCESSING:
                # processing 不因普通 TTL 清理。
                continue
            ttl = (
                COMMITTED_RECEIPT_TTL_SECONDS
                if session.state == STATE_COMMITTED
                else RECEIVING_IDLE_TTL_SECONDS
            )
            # 失败/取消的会话保留一个闲置周期，让客户端还能查询真实结果。
            if now - session.updated_at <= ttl:
                continue
            async with session.lock:
                if session.state != STATE_PROCESSING:
                    self._remove_session(session)

    def recover(self) -> list[str]:
        """服务重启后的会话核对；返回需要人工关注的中文提示。

        receiving 直接失效清理；processing（committing）按正式图库引用
        核对：已引用补写成功回执，未提交清理只属于该会话的候选残留；
        元信息损坏或配置不可读时保留现场并报告，不猜测删除。
        """

        notes: list[str] = []
        if not self._paths.upload_dir.is_dir():
            return notes
        now = time.time()
        for directory in sorted(self._paths.upload_dir.iterdir()):
            if not directory.is_dir():
                continue
            meta_path = directory / "session.json"
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                notes.append(f"上传会话 {directory.name} 记录损坏，已保留待人工核对。")
                continue
            if not isinstance(meta, dict):
                notes.append(f"上传会话 {directory.name} 记录损坏，已保留待人工核对。")
                continue
            state = meta.get("state")
            material_id = str(meta.get("material_id") or "")
            if state == STATE_COMMITTED:
                try:
                    committed_at = float(meta.get("updated_at") or 0)
                except (TypeError, ValueError):
                    notes.append(
                        f"上传会话 {directory.name} 记录损坏，已保留待人工核对。"
                    )
                    continue
                if now - committed_at > COMMITTED_RECEIPT_TTL_SECONDS:
                    self._remove_directory(directory)
                else:
                    # 保留期内的旧回执装入内存：重复查询返回同一历史身份。
                    with suppress(TypeError, ValueError):
                        self._load_receipt_session(meta, directory)
                continue
            if state in {STATE_FAILED, STATE_CANCELLED, STATE_RECEIVING}:
                # 未完成的传输不跨重启续传；失败/取消残留一并清理。
                self._remove_directory(directory)
                continue
            if state != STATE_PROCESSING or not _MATERIAL_ID_PATTERN.fullmatch(
                material_id
            ):
                notes.append(f"上传会话 {directory.name} 状态未知，已保留待人工核对。")
                continue
            try:
                committed_filename = self._hooks.find_committed_material(material_id)
            except Exception:
                # 配置不可读时不能猜测清理可能已入库的素材。
                notes.append(
                    "配置暂不可读，已保留未完成的上传会话，请稍后核对图库。"
                )
                continue
            if committed_filename:
                # 配置已保存但成功回执未落盘：补写回执，只确认历史身份。
                meta["state"] = STATE_COMMITTED
                meta["saved_filename"] = committed_filename
                meta["updated_at"] = now
                with suppress(OSError):
                    (directory / "payload.bin").unlink()
                with suppress(OSError):
                    temp = directory / "session.json.tmp"
                    temp.write_text(
                        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
                    )
                    temp.replace(meta_path)
                with suppress(TypeError, ValueError):
                    self._load_receipt_session(meta, directory)
            else:
                with suppress(Exception):
                    self._hooks.cleanup_candidate(material_id)
                self._remove_directory(directory)
        return notes

    def _load_receipt_session(self, meta: dict, directory: Path) -> None:
        """把磁盘上的成功回执装入内存会话（无 payload、无任务）。"""

        upload_id = str(meta.get("upload_id") or "")
        if not _UPLOAD_ID_PATTERN.fullmatch(upload_id) or upload_id in self._sessions:
            return
        saved_filename = Path(str(meta.get("saved_filename") or "")).name
        self._sessions[upload_id] = UploadSession(
            upload_id=upload_id,
            username=str(meta.get("username") or ""),
            client_request_id=str(meta.get("client_request_id") or ""),
            orientation=str(meta.get("orientation") or "landscape"),
            total_bytes=int(meta.get("total_bytes") or 0),
            display_name=str(meta.get("display_name") or "upload.bin"),
            material_id=str(meta.get("material_id") or ""),
            chunk_size=int(meta.get("chunk_size") or self._chunk_size),
            directory=directory,
            state=STATE_COMMITTED,
            saved_filename=saved_filename,
            received_bytes=int(meta.get("received_bytes") or 0),
            next_index=int(meta.get("next_index") or 0),
            created_at=float(meta.get("created_at") or 0),
            updated_at=float(meta.get("updated_at") or 0),
        )

    async def shutdown(self) -> None:
        """插件重载/终止：取消在途入库任务并等待其真正结束。"""

        tasks = [
            session.task for session in self._sessions.values() if session.task
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task

    # ------------------------------------------------------------------
    # 内部工具

    def _get_session(self, username: str, upload_id: str) -> UploadSession:
        if not _UPLOAD_ID_PATTERN.fullmatch(str(upload_id)):
            raise UploadError("上传会话不存在或已过期。")
        session = self._sessions.get(str(upload_id))
        if session is None or session.username != username:
            raise UploadError("上传会话不存在或已过期。")
        return session

    @staticmethod
    def _parse_index(value: Any) -> int:
        try:
            index = int(str(value), 10)
        except (TypeError, ValueError):
            raise UploadError("分块序号不正确。") from None
        if index < 0:
            raise UploadError("分块序号不正确。")
        return index

    def _total_chunks(self, session: UploadSession) -> int:
        return (session.total_bytes + session.chunk_size - 1) // session.chunk_size

    @staticmethod
    def _chunk_length(session: UploadSession, index: int) -> int:
        start = index * session.chunk_size
        return min(session.chunk_size, session.total_bytes - start)

    def _state_message(self, session: UploadSession) -> str:
        if session.state == STATE_COMMITTED:
            return "素材已加入图库。"
        if session.state == STATE_PROCESSING:
            return "素材正在入库，请稍后查询结果。"
        if session.state == STATE_FAILED:
            return session.error or "素材上传失败，请重新上传。"
        return "上传会话已取消或过期，请重新上传。"

    def _persist_meta(self, session: UploadSession) -> None:
        meta = {
            "upload_id": session.upload_id,
            "username": session.username,
            "client_request_id": session.client_request_id,
            "orientation": session.orientation,
            "total_bytes": session.total_bytes,
            "display_name": session.display_name,
            "material_id": session.material_id,
            "chunk_size": session.chunk_size,
            "state": session.state,
            "saved_filename": session.saved_filename,
            "received_bytes": session.received_bytes,
            "next_index": session.next_index,
            "chunk_digests": session.chunk_digests,
            "error": session.error,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        temp = session.meta_path.with_name("session.json.tmp")
        temp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        temp.replace(session.meta_path)

    def _remove_session(self, session: UploadSession) -> None:
        self._sessions.pop(session.upload_id, None)
        self._remove_directory(session.directory)

    @staticmethod
    def _remove_directory(directory: Path) -> None:
        with suppress(OSError):
            for child in directory.iterdir():
                with suppress(OSError):
                    child.unlink()
            directory.rmdir()
