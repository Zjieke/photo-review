"""Nonblocking process locks, released by the OS if a process crashes."""
import os
import time


def lock(handle, blocking=False):
    if os.name == 'nt':
        import msvcrt
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'\0')
            handle.flush()
        handle.seek(0)
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as error:
                if not blocking:
                    raise BlockingIOError('Already locked') from error
                time.sleep(.05)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))


def unlock(handle):
    if os.name == 'nt':
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_UN)
