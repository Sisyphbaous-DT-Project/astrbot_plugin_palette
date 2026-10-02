"""文件线程的取消边界：清理和关闭句柄前等待真实工作结束。"""

import asyncio
from contextlib import suppress


async def run_file_task(function, *args, **kwargs):
    """取消等待时保留线程任务，工作结束后再把取消传回调用方。"""

    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # asyncio 取消不能停止工作线程；重复取消也不能提前释放文件资源。
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        with suppress(Exception):
            task.result()
        raise
