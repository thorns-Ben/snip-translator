"""智谱 GLM 翻译后端。

优先读取用户保存的设置；未保存时兼容环境变量和源码配置。
没有 key 或调用失败时抛异常，由 ocr_engine 回退到免费接口。
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from . import settings

_API_URL = settings.DEFAULT_API_URL
_DEFAULT_MODEL = settings.DEFAULT_MODEL
_TIMEOUT = 20

_SYSTEM_GENERAL = (
    "你是专业的翻译引擎。把用户给出的文本翻译成目标语言。"
    "只输出译文本身，不要解释、不要加引号、不要复述原文。"
    "保留原文的换行结构和标点。"
)

_SYSTEM_PROGRAMMER = (
    "你是面向程序员的专业翻译引擎。用户给出的是代码或技术文本。\n"
    "绝对规则（优先级最高）：\n"
    "1. 任何标识符都必须逐字符原样保留，禁止翻译、禁止拆分、禁止改写大小写。"
    "标识符包括：变量名、函数名、方法名、类名、参数名、模块名。"
    "只要它在代码里是名字（例如 def 后面的、= 左边的、括号里的参数、点号前后），"
    "就属于标识符，必须原样保留。\n"
    "   例：def upload_file(path) -> 保留 upload_file 和 path\n"
    "   例：current_number 保留，不要变成 当前数字\n"
    "2. 文件路径、URL、命令行参数、版本号、API/产品名原样保留。\n"
    "3. 只翻译自然语言：注释、文档字符串里的说明、散文句子。\n"
    "4. 保留原始缩进和换行结构。\n"
    "5. 只输出结果，不要解释，不要加代码块标记。"
)


def _load_key() -> str:
    return settings.load_settings().api_key


def _load_model() -> str:
    return settings.load_settings().model


def is_available() -> bool:
    """有 key 且没有被显式关闭时可用。"""
    try:
        config = settings.load_settings()
        return config.enabled and bool(config.api_key)
    except settings.SettingsError:
        return False


def _request_settings() -> settings.TranslationSettings:
    config = settings.load_settings()
    if not config.enabled:
        raise RuntimeError("LLM 翻译已关闭")
    if not config.api_key:
        raise RuntimeError("未配置 API Key")
    settings.validate_settings(config)
    return config


def _http_post(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "screenshot-ocr/1.0",
        },
        method="POST",
    )
    try:
        # Do not forward bearer credentials through HTTP redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        safe = {
            400: "HTTP 400：请求格式或模型参数不被服务接受。",
            401: "HTTP 401：API Key 无效或已失效。",
            403: "HTTP 403：当前 Key 没有使用该模型的权限。",
            404: "HTTP 404：接口地址不完整，应以 /chat/completions 结尾。",
            429: "HTTP 429：请求过于频繁或账户额度不足。",
        }.get(exc.code, f"HTTP {exc.code}：翻译服务拒绝了请求。")
        raise RuntimeError(safe) from None
    except (socket.timeout, TimeoutError):
        raise RuntimeError("请求超时：请检查网络或稍后重试。") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise RuntimeError("请求超时：请检查网络或稍后重试。") from None
        raise RuntimeError("网络无法连接：请检查网络和接口地址。") from None
    except Exception:
        raise RuntimeError("LLM 请求失败，请检查网络、地址、模型及凭据。") from None


def translate(text: str, target_lang: str = "zh-Hans", programmer: bool = False) -> str:
    """调用 GLM 翻译。失败抛异常，调用方负责回退。

    target_lang 接受 zh-Hans / en / ja / ko。
    程序员模式下先用占位符保护标识符，翻译后再精确还原，
    避免模型把 upload_file 意译成"上传文件"。
    """
    config = _request_settings()

    lang_name = {
        "zh-Hans": "简体中文",
        "en": "English",
        "ja": "日本語",
        "ko": "한국어",
    }.get(target_lang, "简体中文")

    system = _SYSTEM_PROGRAMMER if programmer else _SYSTEM_GENERAL

    protected = {}
    request_text = text
    if programmer:
        # 复用 OCR 引擎的占位符保护，保证标识符逐字符不变
        from . import ocr_engine as _oe

        request_text, protected = _oe.programmer_prepare(text)

    user = f"目标语言：{lang_name}\n\n{request_text}"

    data = _http_post(
        config.api_url,
        {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "stream": False,
        },
        config.api_key,
        _TIMEOUT,
    )

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("GLM 返回异常")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("GLM 返回空译文")

    if protected:
        from . import ocr_engine as _oe

        content = _oe.restore_code_tokens(content, protected)
    return content


def translate_identifiers(names: list[str], target_lang: str = "zh-Hans") -> dict[str, str]:
    """批量把标识符拆词翻译成中文短语。

    返回 {原标识符: "当前 数量"} 形式。
    """
    config = _request_settings()
    if not names:
        raise RuntimeError("没有待翻译的标识符")

    lang_name = {"zh-Hans": "简体中文", "en": "English"}.get(target_lang, "简体中文")
    listing = "\n".join(names)
    prompt = (
        f"把下面 {len(names)} 个编程标识符按词拆开，分别翻译成{lang_name}，"
        "用空格连接各词。\n"
        "输出格式：每行一个，严格用「原词 => 翻译」的形式，顺序与输入一致，"
        "不要编号，不要解释。\n\n"
        f"{listing}"
    )

    data = _http_post(
        config.api_url,
        {
            "model": config.model,
            "messages": [
                {"role": "system", "content": "你是熟悉编程术语的翻译助手。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "stream": False,
        },
        config.api_key,
        _TIMEOUT,
    )

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("GLM 返回异常")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()

    # 解析「原词 => 翻译」行；对模型偶尔加编号/项目符号做容错
    mapping: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip().lstrip("-*•").strip()
        if not line:
            continue
        for sep in ("=>", "->", "＝>", "：", ":"):
            if sep in line:
                key, _, val = line.partition(sep)
                key = key.strip().strip("`\"' ")
                val = val.strip().strip("`\"' ")
                if key and val:
                    mapping[key] = val
                break

    if not mapping:
        raise RuntimeError("GLM 未返回可解析的翻译")
    return mapping
