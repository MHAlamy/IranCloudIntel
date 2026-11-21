"""Cross-platform exclusive run lock (prevents overlapping scheduled collections).

Uses an O_CREAT|O_EXCL lockfile. A lock older than `stale_after_hours` is
treated as abandoned and reclaimed, so a crashed run cannot deadlock the
collector forever.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


class RunLocked(RuntimeError):
    """Raised when another collection run currently holds the lock."""


class RunLock:
    def __init__(self, path: str | Path, stale_after_hours: float = 6.0):
        self.path = Path(path)
        self.stale_after_seconds = stale_after_hours * 3600
        self._acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self._is_stale():
            try:
                self.path.unlink()  # abandoned lock from a crashed run
            except FileNotFoundError:
                pass  # another process reclaimed it first
        try:
            handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RunLocked(
                f"another collection run holds {self.path}; "
                "if no collector is running, delete the lock file"
            ) from exc
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        self._acquired = True

    def release(self) -> None:
        if self._acquired and self.path.exists():
            self.path.unlink()
        self._acquired = False

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        # shortcut: staleness is time-based, not PID-based; a run longer than
        # stale_after_hours can be reclaimed. Refresh mtime if runs grow long.
        return age > self.stale_after_seconds

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()
