"""
file_lock.py
------------
Tiny shared helper for cross-platform, cross-process exclusive file
locking. Used by any module in this project that does a read-modify-
write on a shared JSON file (history_log.py, error_log.py) so that two
processes writing around the same moment — e.g. the GUI and the
separately-launched shutdown-clean process — can't silently overwrite
each other's entry.

This used to be duplicated inside history_log.py. Pulling it out into
one place means the tricky part (cross-process locking) only has to be
gotten right once, instead of two copies quietly drifting apart over
time as one gets fixed and the other doesn't.

Best-effort: if neither msvcrt (Windows) nor fcntl (POSIX) is
available, locking becomes a no-op rather than raising, matching this
project's existing pattern of gracefully degrading when a platform-
specific facility isn't present (see startup_manager.py's handling of
winreg).
"""

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False


def lock_file(f):
    """Takes an exclusive OS-level lock on file handle `f`, blocking
    until it's free. Every caller locks the same 1-byte region (byte 0)
    so they correctly serialize against each other regardless of the
    file's actual size.
    """
    f.seek(0)
    if _HAS_MSVCRT:
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    elif _HAS_FCNTL:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def unlock_file(f):
    f.seek(0)
    if _HAS_MSVCRT:
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    elif _HAS_FCNTL:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
