"""Translation settings; saved credentials are protected for the current Windows user."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4-flash"


class SettingsError(RuntimeError):
    """A safe, user-facing settings error (never includes stored values)."""


@dataclass(frozen=True)
class TranslationSettings:
    enabled: bool = True
    api_url: str = DEFAULT_API_URL
    model: str = DEFAULT_MODEL
    api_key: str = field(default="", repr=False)


def settings_path() -> Path:
    # Imported lazily so this module itself has no Qt dependency.
    from .paths import app_data_dir

    return Path(app_data_dir()) / "settings.json"


def validate_settings(config: TranslationSettings) -> None:
    """Validate the complete HTTPS endpoint, without echoing user input."""
    if (not isinstance(config, TranslationSettings)
            or type(config.enabled) is not bool
            or not all(isinstance(v, str) for v in
                       (config.api_url, config.model, config.api_key))):
        raise SettingsError("翻译设置格式无效。")
    try:
        url = urlsplit(config.api_url)
        valid = (url.scheme == "https" and bool(url.hostname)
                 and url.username is None and url.password is None
                 and bool(url.path.strip("/")) and not url.fragment
                 and not url.query and url.port != 0
                 and not any(c.isspace() or ord(c) < 32 for c in config.api_url))
    except ValueError:
        valid = False
    if not valid:
        raise SettingsError("请输入完整的 HTTPS API 地址，不含账号、查询参数或片段。")
    if not config.model.strip() or any(ord(c) < 32 for c in config.model):
        raise SettingsError("请输入有效的模型名称。")
    if any(ord(c) < 32 or ord(c) == 127 for c in config.api_key):
        raise SettingsError("API Key 含有无效字符。")


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    if sys.platform != "win32":
        raise SettingsError("凭据保护需要 Windows 当前用户环境。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    blob_ptr = ctypes.POINTER(_DataBlob)
    protect = crypt32.CryptProtectData
    protect.argtypes = [blob_ptr, wintypes.LPCWSTR, blob_ptr, ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, blob_ptr]
    protect.restype = wintypes.BOOL
    unprotect = crypt32.CryptUnprotectData
    unprotect.argtypes = [blob_ptr, ctypes.POINTER(wintypes.LPWSTR), blob_ptr,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr]
    unprotect.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = _DataBlob()
    try:
        # CRYPTPROTECT_UI_FORBIDDEN only; deliberately NOT LOCAL_MACHINE.
        if decrypt:
            ok = unprotect(ctypes.byref(source), None, None, None, None, 1,
                           ctypes.byref(result))
        else:
            ok = protect(ctypes.byref(source), "JietuScreenshot API key", None,
                         None, None, 1, ctypes.byref(result))
        if not ok:
            raise SettingsError("凭据保护失败，请使用保存设置时的 Windows 用户重试。")
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if result.pbData:
            local_free(ctypes.cast(result.pbData, ctypes.c_void_p))


def _legacy_settings() -> TranslationSettings:
    legacy = None
    if not getattr(sys, "frozen", False):
        try:
            legacy = importlib.import_module("llm_config")
        except Exception:
            pass
    key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not key:
        key = str(getattr(legacy, "ZHIPU_API_KEY", "") or "").strip()
    return TranslationSettings(
        enabled=bool(getattr(legacy, "USE_LLM_TRANSLATION", True)),
        model=str(getattr(legacy, "ZHIPU_MODEL", "") or DEFAULT_MODEL),
        api_key=key,
    )


def load_settings() -> TranslationSettings:
    """Saved settings are authoritative, including disabled and empty-key values.

    Corruption raises a sanitized SettingsError; never fall back to a legacy key.
    No settings or legacy credentials are written during loading.
    """
    try:
        path = settings_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _legacy_settings()
        obj = json.loads(raw)
        if (not isinstance(obj, dict) or obj.get("version") != 1
                or set(obj) != {"version", "enabled", "api_url", "model", "api_key_dpapi"}
                or not isinstance(obj["api_key_dpapi"], str)):
            raise ValueError("schema")
        encrypted = obj["api_key_dpapi"]
        key = (_dpapi(base64.b64decode(encrypted, validate=True), decrypt=True)
               .decode("utf-8") if encrypted else "")
        config = TranslationSettings(obj["enabled"], obj["api_url"], obj["model"], key)
        validate_settings(config)
        return config
    except Exception:
        raise SettingsError("翻译设置读取失败或凭据不可解密，请在设置中重新填写并保存。") from None


def save_settings(config: TranslationSettings) -> None:
    """Encrypt before writing, then atomically replace the JSON in the same directory."""
    validate_settings(config)
    temporary = None
    try:
        encrypted = (base64.b64encode(_dpapi(config.api_key.encode("utf-8"))).decode("ascii")
                     if config.api_key else "")
        payload = {"version": 1, "enabled": config.enabled, "api_url": config.api_url,
                   "model": config.model, "api_key_dpapi": encrypted}
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        raise SettingsError("翻译设置保存失败，请检查当前用户权限和凭据保护状态。") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
