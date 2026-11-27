"""Plain-file handles for monthly archive copy/verification/removal.

Windows keeps the exact source and destination open without write/delete sharing.
Removal is by that source handle, never by an unchecked pathname unlink.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
import stat

from .monthly_models import MonthlyArchiveError


def path_key(path):
    return os.path.normcase(os.path.abspath(str(path)))


def plain_path(path, *, missing=False):
    path = Path(os.path.abspath(str(path)))
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise MonthlyArchiveError(f"Datei/Ordner fehlt: {part}")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise MonthlyArchiveError(f"Links/Junctions sind nicht zulässig: {part}")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise MonthlyArchiveError(f"Kein normaler Ordner: {part}")
        if part == path and not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise MonthlyArchiveError(f"Keine normale Datei: {part}")
    return path


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def digest_handle(handle):
    handle.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def inspect_file(path):
    path = plain_path(path)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise MonthlyArchiveError(f"Keine normale Datei: {path}")
        digest = digest_handle(handle)
        if identity(os.fstat(handle.fileno())) != identity(before) or identity(path.stat()) != identity(before):
            raise MonthlyArchiveError(f"Quelle wurde beim Lesen geändert: {path.name}")
        return digest, before.st_size, identity(before)


class PlainHandle:
    def __init__(self, path, *, create=False, write=False, delete=False):
        self.path = plain_path(path, missing=create)
        self.deleted = False
        self.created = create
        self.delete_access = create or write or delete
        self.file = self._open(create=create, write=write or create, delete=self.delete_access)
        self.original_identity = identity(os.fstat(self.file.fileno()))

    def _open(self, *, create=False, write=False, delete=False):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
            kernel.CreateFileW.restype = wintypes.HANDLE
            flags = 0x00200000 | 0x08000000  # OPEN_REPARSE_POINT | SEQUENTIAL_SCAN
            access = 0x80000000 | (0x00010000 if delete else 0) | (0x40000000 if write else 0)
            raw = kernel.CreateFileW(str(self.path), access, 1, None, 1 if create else 3, flags, None)
            if raw == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            fd = msvcrt.open_osfhandle(raw, os.O_BINARY | (os.O_RDWR if write else os.O_RDONLY))
            return os.fdopen(fd, "r+b" if write else "rb")
        else:
            handle = self.path.open("x+b" if create else "r+b" if write else "rb")
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle

    def verify(self, sha256, *, expected_identity=None):
        before = identity(os.fstat(self.file.fileno()))
        if expected_identity is not None and before != tuple(expected_identity):
            raise MonthlyArchiveError(f"Dateiidentität geändert: {self.path.name}")
        if digest_handle(self.file) != sha256 or identity(os.fstat(self.file.fileno())) != before:
            raise MonthlyArchiveError(f"SHA-Prüfung fehlgeschlagen: {self.path.name}")
        if identity(plain_path(self.path).stat()) != before:
            raise MonthlyArchiveError(f"Dateipfad wurde ersetzt: {self.path.name}")

    def copy_from(self, source):
        self.file.seek(0)
        self.file.truncate()
        source.file.seek(0)
        for chunk in iter(lambda: source.file.read(1024 * 1024), b""):
            self.file.write(chunk)
        self.file.flush()
        os.fsync(self.file.fileno())

    def publish(self, target):
        """Atomic no-overwrite publication of our private completed copy."""
        target = plain_path(target, missing=True)
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            units = len(str(target).encode("utf-16-le")) // 2 + 1
            class RenameInfo(ctypes.Structure):
                _fields_ = [("ReplaceIfExists", wintypes.BOOLEAN), ("RootDirectory", wintypes.HANDLE),
                            ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * units)]
            info = RenameInfo(False, None, len(str(target).encode("utf-16-le")), str(target))
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
            kernel.SetFileInformationByHandle.restype = wintypes.BOOL
            if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(self.file.fileno()), 3,
                                                     ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            os.link(self.path, target)
            self.path.unlink()
        self.path = target

    def remove(self, expected_sha256):
        if os.name == "nt" and not self.delete_access:
            # Keep normal reads possible while copying. Upgrade by reopening
            # and revalidate exact inode+SHA: a replacement in this tiny window
            # must never be removed. The final DELETE handle pins that identity.
            self.file.close()
            self.file = self._open(delete=True)
            self.delete_access = True
        self.verify(expected_sha256, expected_identity=self.original_identity if not self.created else None)
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
            kernel.SetFileInformationByHandle.restype = wintypes.BOOL
            delete = wintypes.BOOL(True)
            raw = msvcrt.get_osfhandle(self.file.fileno())
            if not kernel.SetFileInformationByHandle(raw, 4, ctypes.byref(delete), ctypes.sizeof(delete)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.deleted = True
        else:
            import uuid
            quarantine = self.path.with_name(f".arev2-remove-{uuid.uuid4().hex}")
            os.rename(self.path, quarantine)
            if identity(quarantine.stat()) != identity(os.fstat(self.file.fileno())):
                if not self.path.exists():
                    os.link(quarantine, self.path)
                    quarantine.unlink()
                raise MonthlyArchiveError("Quelle wurde vor Entfernen ersetzt; Ersatzdatei bleibt erhalten.")
            quarantine.unlink()
            self.deleted = True

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def create_directories(path):
    path = plain_path(path, missing=True)
    path.mkdir(parents=True, exist_ok=True)
    plain_path(path)
    return path
