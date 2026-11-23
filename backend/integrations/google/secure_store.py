"""Current-Windows-user DPAPI encryption. No plaintext or portable-key fallback."""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile

from backend.integrations.google.common import GoogleError


def dpapi(data: bytes, decrypt=False):
    if os.name != 'nt':
        raise GoogleError('Secure Google credential storage requires Windows DPAPI on this version.', 503)
    class Blob(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise GoogleError('Windows could not protect or unlock the Google credentials for this user.', 503)
    try:
        return ctypes.string_at(target.data, target.length)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, wintypes.HLOCAL))


class SecureStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, name):
        if name not in {'client', 'calendar', 'gmail', 'classroom'}:
            raise GoogleError('Unknown credential slot.', 400)
        path = self.directory / (name + '.dpapi')
        # Never follow a credential directory/file replaced by a link.
        for part in (path, *path.parents):
            if part.exists() and (part.is_symlink() or bool(getattr(part.lstat(), 'st_file_attributes', 0) & 0x400)):
                raise GoogleError('Credential storage cannot use linked paths.', 503)
        return path

    def has(self, name):
        return self._path(name).is_file()

    def load(self, name):
        path = self._path(name)
        if not path.exists():
            return None
        try:
            data = path.read_bytes()
            if len(data) > 65536:
                raise ValueError()
            value = json.loads(dpapi(data, decrypt=True))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (OSError, ValueError):
            raise GoogleError('Stored Google credentials are unavailable or invalid. Re-import or reconnect.', 503)

    def save(self, name, value):
        # Encrypt before any write, and atomically replace only our own credential blob.
        protected = dpapi(json.dumps(value).encode('utf-8'))
        path = self._path(name)
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(protected)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError:
            raise GoogleError('Secure credential storage is not writable.', 503)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def forget(self, name):
        try:
            self._path(name).unlink(missing_ok=True)
        except OSError:
            raise GoogleError('The local encrypted credentials could not be removed.', 503)
