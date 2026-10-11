"""A single service owns recovery and the local queue for a data directory."""
from pathlib import Path
import os


class RuntimeLock:
    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        try:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError('同一数据目录已有 Web 服务运行；请使用已有服务或先关闭它。正在生成的任务保持运行。') from exc
        self.file = handle
        return self

    def __exit__(self, *_):
        if self.file is not None:
            self.file.close()  # OS also releases the lock on process termination.
            self.file = None
