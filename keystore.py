"""Meta API key storage for the HD520 companion. Standard library only.

Storage, in order of preference:

  Windows: Windows Credential Manager, via ctypes calls to CredWriteW,
  CredReadW, and CredDeleteW. No new dependency. Target name:
  "HD520Companion/MetaApiKey", generic credential, persisted on the
  local machine.

  Any other OS, or if the vault call fails on Windows: a file with
  0600 permissions under the per-user config dir, at
  <config>/HD520Companion/meta_key. On Windows the fallback dir is
  %APPDATA%; on macOS it is ~/Library/Application Support; on Linux
  it is ~/.config.

Only this module and the settings endpoint touch the stored key. The
key is never printed, logged, written to a job file, cut list, DXF,
or export. The settings status endpoints report only whether a key
is stored and where, never the key itself.

Test isolation override: when env HD520_KEYSTORE_DIR is set, the
keystore becomes file-only inside that directory and the Windows
vault is bypassed entirely (get, set, delete, and source). That is
what lets the parity suite run against an empty store on a machine
that has a real key saved. When the variable is unset, behavior is
exactly as described above; the override never moves the jobs/data
dir, only the key file.

Delete clears both stores, so a deleted key cannot resurface from
the other store. Set writes to the preferred store and clears the
other store, so the two can never disagree.

Effective Meta key precedence, resolved by the servers:
  stored key > env HD520_META_API_KEY > env META_API_KEY.
"""

import ctypes
import os
import sys
from pathlib import Path

TARGET_NAME = "HD520Companion/MetaApiKey"
APP_DIR_NAME = "HD520Companion"
FILE_NAME = "meta_key"

# Generic credential type and local-machine persistence, per wincred.h.
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


def config_dir():
    """Per-user config dir for this app, by platform."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base)
    return Path.home() / ".config"


def user_data_dir():
    """Per-user data dir for this app (jobs live here in desktop mode)."""
    return config_dir() / APP_DIR_NAME


def _override_dir():
    """HD520_KEYSTORE_DIR test-isolation dir, or None when unset."""
    raw = os.environ.get("HD520_KEYSTORE_DIR")
    if raw and raw.strip():
        return Path(raw.strip())
    return None


def _file_path():
    override = _override_dir()
    if override is not None:
        return override / FILE_NAME
    return user_data_dir() / FILE_NAME


def _file_get():
    try:
        path = _file_path()
        if not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def _file_set(key):
    path = _file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(key)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _file_delete():
    try:
        _file_path().unlink()
    except OSError:
        pass


if sys.platform == "win32":
    import ctypes.wintypes as _wintypes

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", _wintypes.DWORD),
                    ("dwHighDateTime", _wintypes.DWORD)]

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [("Flags", _wintypes.DWORD),
                    ("Type", _wintypes.DWORD),
                    ("TargetName", _wintypes.LPWSTR),
                    ("Comment", _wintypes.LPWSTR),
                    ("LastWritten", _FILETIME),
                    ("CredentialBlobSize", _wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", _wintypes.DWORD),
                    ("AttributeCount", _wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", _wintypes.LPWSTR),
                    ("UserName", _wintypes.LPWSTR)]

    try:
        _advapi32 = ctypes.windll.advapi32
        _advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW),
                                         _wintypes.DWORD]
        _advapi32.CredWriteW.restype = _wintypes.BOOL
        _advapi32.CredReadW.argtypes = [_wintypes.LPCWSTR, _wintypes.DWORD,
                                        _wintypes.DWORD,
                                        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        _advapi32.CredReadW.restype = _wintypes.BOOL
        _advapi32.CredDeleteW.argtypes = [_wintypes.LPCWSTR, _wintypes.DWORD,
                                          _wintypes.DWORD]
        _advapi32.CredDeleteW.restype = _wintypes.BOOL
        _advapi32.CredFree.argtypes = [ctypes.c_void_p]
        _advapi32.CredFree.restype = None
        _VAULT_AVAILABLE = True
    except (AttributeError, OSError):
        _VAULT_AVAILABLE = False

    def _vault_get():
        if not _VAULT_AVAILABLE:
            return None
        cred_ptr = ctypes.POINTER(_CREDENTIALW)()
        ok = _advapi32.CredReadW(TARGET_NAME, _CRED_TYPE_GENERIC, 0,
                                 ctypes.byref(cred_ptr))
        if not ok or not cred_ptr:
            return None
        try:
            cred = cred_ptr.contents
            size = cred.CredentialBlobSize
            if not size or not cred.CredentialBlob:
                return None
            raw = ctypes.string_at(cred.CredentialBlob, size)
            value = raw.decode("utf-16-le", errors="strict").strip()
            return value or None
        except (ValueError, UnicodeDecodeError):
            return None
        finally:
            _advapi32.CredFree(cred_ptr)

    def _vault_set(key):
        if not _VAULT_AVAILABLE:
            return False
        blob = key.encode("utf-16-le")
        buf = ctypes.create_string_buffer(blob, len(blob))
        cred = _CREDENTIALW()
        cred.Flags = 0
        cred.Type = _CRED_TYPE_GENERIC
        cred.TargetName = TARGET_NAME
        cred.Comment = None
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = 0
        cred.Attributes = None
        cred.TargetAlias = None
        cred.UserName = None
        return bool(_advapi32.CredWriteW(ctypes.byref(cred), 0))

    def _vault_delete():
        if not _VAULT_AVAILABLE:
            return
        _advapi32.CredDeleteW(TARGET_NAME, _CRED_TYPE_GENERIC, 0)

else:
    _VAULT_AVAILABLE = False

    def _vault_get():
        return None

    def _vault_set(key):
        return False

    def _vault_delete():
        return


def vault_available():
    """True when the Windows Credential Manager path can be used."""
    return _VAULT_AVAILABLE


def get_meta_key():
    """Return the stored Meta key, or None. Never logs or prints it."""
    if _override_dir() is not None:
        return _file_get()
    value = _vault_get()
    if value:
        return value
    return _file_get()


def meta_key_source():
    """Where a stored key lives: "vault", "file", or None. No key value."""
    if _override_dir() is not None:
        return "file" if _file_get() else None
    if _vault_get():
        return "vault"
    if _file_get():
        return "file"
    return None


def set_meta_key(key):
    """Store a Meta key. Raises ValueError on an empty key."""
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Meta key must be a non-empty string.")
    key = key.strip()
    if _override_dir() is not None:
        _file_set(key)
    elif _vault_set(key):
        _file_delete()
    else:
        _file_set(key)


def delete_meta_key():
    """Remove the stored Meta key from both stores."""
    if _override_dir() is not None:
        _file_delete()
        return
    _vault_delete()
    _file_delete()
