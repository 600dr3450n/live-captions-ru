"""Single-instance guard based on a named Windows mutex."""
from __future__ import annotations

import ctypes
import logging
import time

from config import MUTEX_NAME

log = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183

# The mutex has to outlive the check, so the handle is kept for the process lifetime.
# Releasing it would drop the guard and let a second copy start.
_HANDLE = None


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_bool
    return kernel32


def already_running() -> bool:
    """Single-instance guard via a named mutex.

    On any failure we assume "not running" — otherwise the app would refuse to start
    for a user without the required privileges.
    """
    global _HANDLE
    if _HANDLE is not None:
        # We are the owner: the same process asking twice is still "already running".
        return True
    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        log.warning("mutex_create_failed error=%s action=continue", ctypes.get_last_error())
        return False
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        # Another process owns the mutex: keep the guard, drop our extra handle so it
        # does not leak on every check.
        kernel32.CloseHandle(handle)
        return True
    _HANDLE = handle
    return False


def wait_until_free(timeout: float, poll: float = 0.25) -> bool:
    """Wait for the previous instance to let go of the mutex.

    Used by the self relaunch: the new process must not start a second pipeline, and
    a fixed sleep is a guess. Returns True when the mutex became ours, False when the
    previous instance is still alive after `timeout` seconds. On success the caller
    owns the mutex and must not call already_running() again.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if not already_running():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)


