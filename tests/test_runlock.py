"""Tests for the exclusive run lock."""

import os
import time

import pytest

from util.runlock import RunLock, RunLocked


def test_acquire_release_reacquire(tmp_path):
    lock = RunLock(tmp_path / "lock")
    with lock:
        assert (tmp_path / "lock").exists()
    assert not (tmp_path / "lock").exists()  # released
    with lock:  # can be reacquired
        pass


def test_second_holder_rejected(tmp_path):
    with RunLock(tmp_path / "lock"):
        with pytest.raises(RunLocked):
            RunLock(tmp_path / "lock").acquire()


def test_stale_lock_is_reclaimed(tmp_path):
    stale = RunLock(tmp_path / "lock", stale_after_hours=0.0001)  # ~0.36s
    with stale:
        time.sleep(0.5)
        fresh = RunLock(tmp_path / "lock", stale_after_hours=0.0001)
        with fresh:  # stale lock reclaimed without error
            pass
    assert not (tmp_path / "lock").exists()


def test_lock_records_pid(tmp_path):
    with RunLock(tmp_path / "lock"):
        content = (tmp_path / "lock").read_text()
        assert content == str(os.getpid())
