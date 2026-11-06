"""OCR 引擎 + 文本行重排 + 在线翻译（无 key）。"""

import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

import cv2
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from .programming_glossary import (
    WORDS as _PROGRAMMING_GLOSSARY,
    PHRASES as _PROGRAMMING_PHRASES,
)

# RapidOCR 每次建 session 都会打 INFO 日志，压掉
logging.getLogger("OrtInferSession").setLevel(logging.ERROR)

_engine = None

# 实测：默认参数(intra=-1, limit_type=min)在小图上会把图放大到 736 长边，
# 反而比原尺寸慢 4~5 倍。改成 max 限制 + 物理核数个线程。
_DET_MAX_SIDE = 1280
_UPSCALE_BELOW = 640


def _has_dml() -> bool:
    try:
        import onnxruntime as ort

        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _build_engine() -> RapidOCR:
    threads = max(2, min(8, (os.cpu_count() or 4) // 2))
    use_dml = _has_dml()  # Windows + onnxruntime-directml，实测约 5x 加速

    return RapidOCR(
        intra_op_num_threads=threads,
        inter_op_num_threads=1,
        use_cls=False,                 # 横排截图不需要方向分类，省一次推理
        det_limit_type="max",          # 关键：小图不放大（默认 min 会放大到 736）
        det_limit_side_len=_DET_MAX_SIDE,
        rec_batch_num=6,
        det_use_dml=use_dml,
        rec_use_dml=use_dml,
    )


# RapidOCR 实例不是线程安全的：选区防抖会并发起多个识别线程，
# 必须串行化，否则可能崩溃或串结果。
_ENGINE_LOCK = threading.RLock()
_INFER_LOCK = threading.RLock()


def get_engine() -> RapidOCR:
    """首次调用会加载模型（约 0.5~1 秒），之后复用。"""
    global _engine
    with _ENGINE_LOCK:
        if _engine is None:
            _engine = _build_engine()
            # get_logger() 会强制把级别设回 DEBUG，只能建完后再压
            for name in ("OrtInferSession", "RapidOCR"):
                logging.getLogger(name).setLevel(logging.ERROR)
        return _engine


def preload() -> None:
    """加载模型并跑一次真实推理，把 DirectML 首次开销放到启动阶段。"""
    get_engine()
    try:
        # 造一张小图跑完整链路（det + rec），否则第一次框选还要多等 ~400ms
        dummy = np.full((48, 240, 3), 255, dtype=np.uint8)
        cv2.putText(dummy, "warmup", (8, 34), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (0, 0, 0), 2)
        recognize(Image.fromarray(cv2.cvtColor(dummy, cv2.COLOR_BGR2RGB)))
    except Exception:
        pass
    try:
        translate("warm up", mode="general")
    except Exception:
        pass


# ---------------------------------------------------------------- 文本行重排
def _is_word_char(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in "'-_.@/:#+&%=~")


def _smart_join(parts):
    """中文直接拼接；英文单词之间补空格。

    判据用「两侧都是 ASCII 词字符」而不是 alnum，
    否则 'fox' + 'jumps' 这种被检测框切开的英文会粘在一起。
    """
    out = ""
    for p in parts:
        if not p:
            continue
        if not out:
            out = p
        elif _is_word_char(out[-1]) and _is_word_char(p[0]):
            out += " " + p
        else:
            out += p
    return out


def _layout(items) -> str:
    rows = []
    for box, text, score in items:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        rows.append(
            {
                "x0": min(xs),
                "cy": (min(ys) + max(ys)) / 2,
                "h": max(ys) - min(ys),
                "text": text,
                "score": score,
            }
        )
    if not rows:
        return ""

    rows.sort(key=lambda r: r["cy"])
    lines = []
    for r in rows:
        if lines:
            last = lines[-1]
            tol = max(8.0, 0.55 * max(r["h"], last["h"]))
            if abs(r["cy"] - last["cy"]) <= tol:
                last["items"].append(r)
                old = last["cy"]
                last["cy"] = (old * (len(last["items"]) - 1) + r["cy"]) / len(last["items"])
                last["h"] = max(last["h"], r["h"])
                continue
        lines.append({"cy": r["cy"], "h": r["h"], "items": [r]})

    out = []
    for ln in lines:
        ln["items"].sort(key=lambda r: r["x0"])
        out.append(_smart_join([i["text"] for i in ln["items"]]).strip())
    return "\n".join(out)


def _prepare(arr: np.ndarray) -> np.ndarray:
    """长边过小时放大，明显提升小字号识别率。"""
    h, w = arr.shape[:2]
    long_side = max(h, w)
    if long_side < _UPSCALE_BELOW:
        scale = min(3.0, _UPSCALE_BELOW / long_side)
        arr = cv2.resize(
            arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC
        )
    return arr


# 实测：识别模型对紧贴文字边缘的裁剪会吞掉空格。
# pad 0~3 空格丢失，4~7 全对，>=8 反而开始粘连/漏字。取区间中位数 6。
_REC_PAD = 6


# ---------------------------------------------------------------- 下划线修复
def _find_underscores(crop_bgr: np.ndarray) -> int:
    """在原始分辨率的字形图上判断这一行有几条下划线。

    实测行剖面（26px 字体，原图裁剪）：
        upload_file  r53: [3, 11]   r54: [12]      <- 下划线（单段 12px）
        ocr engine   r51: [2, 4]    r52: [10]      <- g 的下伸部（会继续往下）
        hello world  r24-26: 1px 噪声

    判据（三条同时满足）：
      1) 该行是整幅图的 **最后一两行**（下划线贴着字底）
      2) 该行存在单段宽度 >= 字高 * 0.3 的连续列
      3) 该行下方没有更多墨迹（排除 p/g/y 下伸部）
    """
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    if float(np.median(gray)) < 128:
        gray = 255 - gray

    _thr, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (binary > 0).astype(np.uint8)
    if ink.sum() < 5:
        return 0

    row_ink = ink.sum(axis=1)
    rows = np.where(row_ink > 0)[0]
    if len(rows) == 0:
        return 0

    top, bottom = int(rows[0]), int(rows[-1])
    h = bottom - top + 1
    if h < 8:
        return 0

    width = crop_bgr.shape[1]
    # 实测：下划线单段宽度 = 字高 * 0.4 左右；字母横向笔画最大 0.2~0.3
    min_run = max(6, int(h * 0.35))
    # 同一行的下划线之间至少隔一个字符宽度，超过这个距离就算两条
    gap_merge = max(8, int(h * 1.2))

    # 从最底部往上扫最多 3 行，找"下方无墨 + 有宽连续段"的行
    for offset in range(0, 3):
        r = bottom - offset
        if r < top:
            break
        below = ink[r + 1 : bottom + 1, :]
        if below.size and below.sum() > 0:
            continue                     # 下面还有墨 -> 是下伸部，不是下划线

        cols = np.where(ink[r, :] > 0)[0]
        if len(cols) == 0:
            continue

        # 收集 (起点, 宽度)，保留位置以便判断"两条下划线"还是"一条被断开"
        spans, start = [], None
        col_set = set(int(c) for c in cols)
        for c in range(int(cols[0]), int(cols[-1]) + 2):
            if c in col_set:
                if start is None:
                    start = c
            elif start is not None:
                spans.append((start, c - start))
                start = None

        wide = [(s, w) for s, w in spans if w >= min_run]
        if not wide:
            continue

        # 下划线特征：本行只有很少几段墨迹，且达标段是孤立的
        # 自然语言单词下沿（hello world）会有 10+ 段密集笔画
        if len(spans) > 4:
            continue

        # 相邻且间隙很小的段视为同一条下划线（抗锯齿断点），否则算两条
        count = 1
        prev_start, prev_w = wide[0]
        for s, w in wide[1:]:
            if s - (prev_start + prev_w) > gap_merge:
                count += 1
            prev_start, prev_w = s, w
        return count

    return 0


def _fix_baseline_chars(ocr_text: str, crop_bgr: np.ndarray) -> str:
    """OCR 常把下划线识别成空格（或漏掉）。

    用图像特征确认下划线个数，再把对应位置的空格换回下划线。
    只处理纯 ASCII 标识符，避免影响中文。
    crop_bgr 必须是 **原始分辨率** 的裁剪图（放大图会丢失 1px 下划线）。
    """
    count = _find_underscores(crop_bgr)
    if count <= 0:
        return ocr_text
    if not ocr_text or not ocr_text.isascii():
        return ocr_text

    # 模型已正确输出下划线，无需修复
    if "_" in ocr_text:
        return ocr_text

    parts = ocr_text.split()
    if len(parts) - 1 != count:
        return ocr_text

    # 只在片段都是标识符字符时拼接
    if not all(p and all(ch.isalnum() or ch in "._-/" for ch in p) for p in parts):
        return ocr_text

    return "_".join(parts)


def recognize(pil_image: Image.Image, min_score: float = 0.4) -> str:
    arr = np.array(pil_image.convert("RGB"))
    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    prepared = _prepare(arr)          # 放大版：用于检测/识别（准确率高）
    engine = get_engine()
    with _INFER_LOCK:                 # RapidOCR 非线程安全，串行执行
        boxes, _ = engine.text_det(prepared)
        if boxes is None or len(boxes) == 0:
            return ""

        crops = engine.get_crop_img_list(prepared, boxes)
        padded = [
            cv2.copyMakeBorder(c, _REC_PAD, _REC_PAD, _REC_PAD, _REC_PAD,
                               cv2.BORDER_CONSTANT, value=(255, 255, 255))
            if c.size else c
            for c in crops
        ]
        results, _ = engine.text_rec(padded)

    # 下划线检测必须在 **原始分辨率** 图上看：放大 2~3 倍会把 1px 下划线插值糊掉
    ratio = arr.shape[1] / prepared.shape[1] if prepared.shape[1] else 1.0
    ah, aw = arr.shape[:2]
    raw_crops = []
    for box in boxes:
        xs = [float(p[0]) * ratio for p in box]
        ys = [float(p[1]) * ratio for p in box]
        x0 = max(0, int(min(xs)))
        y0 = max(0, int(min(ys)))
        x1 = min(aw, int(max(xs)) + 1)
        y1 = min(ah, int(max(ys)) + 1)
        # 检测框常把下划线切掉（下划线位于基线略下方）。
        # 向下扩几像素再取裁剪图，避免漏检；同时左右留 2px 余量。
        pad_y = max(3, int((y1 - y0) * 0.35))
        y0x = max(0, y0 - 2)
        y1x = min(ah, y1 + pad_y)
        x0x = max(0, x0 - 2)
        x1x = min(aw, x1 + 2)
        raw_crops.append(
            arr[y0x:y1x, x0x:x1x]
            if x1x > x0x and y1x > y0x else np.empty((0, 0, 3), np.uint8)
        )

    items = []
    for idx, (box, (text, score)) in enumerate(zip(boxes, results)):
        if not text.strip():
            continue
        if score is not None and score < min_score:
            continue
        if idx < len(raw_crops) and raw_crops[idx].size:
            text = _fix_baseline_chars(text, raw_crops[idx])
        items.append((box, text, score))
    return _layout(items).strip()


# ---------------------------------------------------------------- 翻译
_CJK = re.compile(r"[\u4e00-\u9fff]")
_CODE_TOKEN = re.compile(
    r"(?:```[\s\S]*?```|`[^`\n]+`|"                # fenced / inline code
    r"https?://[^\s<>()\[\]{}'\"]+|"               # URL
    r"(?:[A-Za-z]:)?[\\/](?:[^\s\\/:*?\"<>|]+[\\/]?)+|"   # 绝对/相对路径
    r"(?:\.\.?/)?[\w.-]+(?:[\\/]\w[\w.-]*)+|"      # 带斜杠的相对路径
    r"--?[A-Za-z][\w-]*(?:=[^\s]+)?|"              # 命令行参数
    r"[A-Z]{2,}[A-Za-z0-9]*|"                      # 全大写技术词
    r"[A-Za-z]+\d+\w*|"                            # 含数字的标识符
    r"[A-Za-z]+(?:[A-Z][A-Za-z0-9]+)+|"            # PascalCase
    r"[A-Za-z][A-Za-z0-9]*[_-][A-Za-z0-9_-]+|"     # snake/kebab
    r"[A-Za-z_]\w*\.[A-Za-z_]\w*(?:\([^()\n]*(?:\([^()\n]*\)[^()\n]*)*\))?|"  # qualified / 调用
    r"\b(?:v?\d+(?:\.\d+){1,3}|[A-Za-z][\w-]*>=?\d+(?:\.\d+)*)\b|"
    r"\b(?:def|class|import|from|async|await|lambda|yield|"
    r"elif|else|except|finally|None|True|False|"
    r"self|str|int|float|bool|list|dict|tuple|set)\b|"
    r"[A-Za-z_]\w*\s*(?==)|"                       # 关键字参数 / 赋值左侧
    r"[()\[\]{}<>|&*+=/\\:;,])"                    # 代码标点（避免被翻译）
)

# 占位符：必须足够"不像正常文本"，否则译文里合法的 [2] / 【2】
# 会被误当成占位符替换掉。用双全角括号 + 字母前缀 + 数字。
_PLACEHOLDER = "〔〔zq{}〕〕"
_PLACEHOLDER_RE = re.compile(r"[〔\[【]\s*[〔\[【]\s*z\s*q\s*(\d+)\s*[〕\]】]\s*[〕\]】]",
                             re.IGNORECASE)


def normalize_text(text: str, programmer_mode: bool = False) -> str:
    """安全规范化；程序员模式只做 Unicode 规范化，保留缩进与空行。"""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    if programmer_mode:
        # 只去掉整体首尾空行，保留行首缩进（代码语义）
        return text.strip("\n")
    return "\n".join(
        re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")
    ).strip()


_LANGUAGE_CODES = {
    "自动": "auto", "中文": "zh-Hans", "简体中文": "zh-Hans", "英语": "en",
    "英文": "en", "日文": "ja", "韩文": "ko",
    "auto": "auto", "zh": "zh-Hans", "zh-hans": "zh-Hans",
    "zh-cn": "zh-Hans", "en": "en", "ja": "ja", "ko": "ko",
}


def language_code(label: str) -> str:
    return _LANGUAGE_CODES.get((label or "").strip().lower(), label or "auto")


def _target_lang(text: str, source: str = "auto", target: str = "zh-Hans") -> str:
    if target and target != "auto":
        return target
    stripped = re.sub(r"\s", "", text)
    if not stripped:
        return "zh-Hans"
    cjk = len(_CJK.findall(stripped))
    return "en" if cjk / len(stripped) > 0.25 else "zh-Hans"


def protect_code_tokens(text: str) -> tuple[str, dict[str, str]]:
    """保护代码 token，返回 (带占位符的文本, 恢复表)。

    尾随标点（. , ; : ! ? )）留在占位符外面，
    否则会把句号一起"保护"进代码，译文里就丢掉标点了。
    """
    protected: dict[str, str] = {}

    def save_match(m):
        raw = m.group(0)
        # 只剥离句子标点；括号/引号是代码的一部分，不能剥
        core = raw.rstrip(".,;:!?")
        if not core:
            return raw          # 空 token 直接原样返回，不建占位符
        tail = raw[len(core):]
        key = _PLACEHOLDER.format(len(protected))
        protected[key] = core
        return key + tail

    text = _CODE_TOKEN.sub(save_match, text)
    return text, protected


def restore_code_tokens(text: str, protected: dict[str, str]) -> str:
    """恢复占位符。

    翻译器常把全角〔〕转成半角 []，也偶尔插空格，
    所以按"数字索引"匹配，兼容两种括号和空白。
    """
    index_map = {}
    for idx, value in enumerate(protected.values()):
        index_map[idx] = value

    def repl(m):
        idx = int(m.group(1))
        return index_map.get(idx, m.group(0))

    return _PLACEHOLDER_RE.sub(repl, text)


def programmer_prepare(text: str) -> tuple[str, dict[str, str]]:
    return protect_code_tokens(normalize_text(text, programmer_mode=True))


def validate_protected_tokens(text: str, protected: dict[str, str]) -> bool:
    """校验恢复后的文本。

    翻译器偶尔会吞掉个别占位符（例如把 〔2〕 直接删掉）。
    这种情况不应让整次翻译失败——只要原文其余部分正常，
    就降级为"少一个 token"而不是抛错。
    """
    if not protected:
        return True
    values = [v for v in protected.values() if v]
    if not values:
        return True
    missing = [v for v in values if v not in text]
    # 丢失超过 1/3 才认为恢复失败
    return len(missing) <= max(1, len(values) // 3)


_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}


def _http(url, data=None, headers=None, timeout=8):
    h = dict(_UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _youdao_codes(source: str, to: str) -> tuple[str, str]:
    """有道用 zh-CHS；且只支持 Auto 自动判方向，显式 en 会报 102。"""
    src = "Auto" if source == "auto" else ("zh-CHS" if source.startswith("zh") else source)
    if to.startswith("zh"):
        dst = "zh-CHS"
    else:
        dst = "Auto"        # 有道不接受显式目标语言（除中文外）
    if src == "Auto" and dst == "Auto":
        src = "Auto"
    return src, dst


def _translate_youdao(text: str, to: str, source: str = "auto") -> str:
    """有道公开演示接口，无需 key。"""
    src, dst = _youdao_codes(source, to)
    url = (
        "https://aidemo.youdao.com/trans?q="
        + urllib.parse.quote(text)
        + f"&from={urllib.parse.quote(src)}&to={urllib.parse.quote(dst)}"
    )
    data = json.loads(_http(url).decode("utf-8"))
    if str(data.get("errorCode")) != "0":
        raise RuntimeError(f"errorCode={data.get('errorCode')}")
    parts = data.get("translation") or []
    return "".join(parts)


def _translate_google(text: str, to: str, source: str = "auto") -> str:
    tl = "zh-CN" if to.startswith("zh") else to
    sl = "auto" if source == "auto" else source
    url = (
        "https://translate.google.com/translate_a/single?client=gtx"
        f"&sl={sl}&tl={tl}&dt=t&q={urllib.parse.quote(text)}"
    )
    data = json.loads(_http(url).decode("utf-8"))
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


# ---------------------------------------------------------------- 标识符拆解
# 匹配标识符：snake_case / kebab-case / camelCase / PascalCase / 带数字
_IDENT_RE = re.compile(
    r"(?<!\w)_[A-Za-z0-9_]+\b"                            # private / dunder
    r"|\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b"     # snake / kebab
    r"|\b[A-Za-z]+(?:[A-Z][A-Za-z0-9]+)+\b"                 # camel / Pascal
)

# 拆词后不值得翻译的常见噪声
_STOPWORDS = {"a", "an", "the", "of", "to", "for", "and", "or", "is", "in", "on"}


def split_identifier(name: str) -> list[str]:
    """把标识符拆成单词。

    current_number -> ['current', 'number']
    currentNumber  -> ['current', 'Number']
    ImportGraphState -> ['Import', 'Graph', 'State']
    HTTPResponse   -> ['HTTP', 'Response']
    """
    if not name:
        return []

    # 先按下划线/连字符拆
    parts: list[str] = []
    for chunk in re.split(r"[_-]+", name):
        if not chunk:
            continue
        # 再按驼峰拆：大写字母边界、连续大写后跟小写（HTTPResponse -> HTTP + Response）
        for piece in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", chunk):
            parts.append(piece)
    return [p for p in parts if p]


def find_identifiers(text: str, min_parts: int = 2) -> list[str]:
    """找出文本中值得拆解翻译的标识符（至少能拆成 2 个词）。"""
    seen: list[str] = []
    for m in _IDENT_RE.finditer(text):
        token = m.group(0)
        if token in seen:
            continue
        if token.isupper() and len(token) <= 4:
            continue          # API / HTTP 这类缩写不拆
        if len(split_identifier(token)) >= min_parts:
            seen.append(token)
    return seen


def is_identifier_dominated(text: str, threshold: float = 0.7) -> bool:
    """判断文本是否"几乎只有标识符"，没有值得翻译的自然语言。

    判据：标识符覆盖的字符占比高，且不存在 3 个以上连续的自然语言单词。
    """
    stripped = re.sub(r"\s", "", text)
    if not stripped:
        return False

    covered = sum(len(m.group(0)) for m in _IDENT_RE.finditer(text))
    if covered / len(stripped) < threshold:
        return False

    # 去掉标识符后，看是否还有成句的自然语言
    residual = _IDENT_RE.sub(" ", text)
    words = [w for w in re.findall(r"[A-Za-z]{2,}", residual) if w.lower() not in _STOPWORDS]
    return len(words) < 3


def _standalone_identifiers(text: str) -> bool:
    """Explanation-only output must never discard assignments, calls or operators."""
    tokens = re.split(r"[\s,]+", text.strip())
    return bool(tokens) and all(
        token and _IDENT_RE.fullmatch(token)
        and len(split_identifier(token)) >= 2
        for token in tokens
    )


def build_explanation(ident: str, translated_parts: list[str]) -> str:
    """生成 'current_number = 当前的 数字' 形式的一行说明。"""
    parts = split_identifier(ident)
    if not parts or len(translated_parts) != len(parts):
        return ""
    joined = " ".join(t.strip() for t in translated_parts if t.strip())
    if not joined:
        return ""
    return f"{ident} = {joined}"


# 常见编程术语：免费翻译接口在技术语境下会翻错（import→进口），
# 这里优先用固定映射，既快又准。


def local_programming_translation(text: str) -> str | None:
    """只接受完整术语或可全部拆解的标识符，未知词不猜译。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or len(lines) > 32:
        return None
    results = []
    for line in lines:
        key = re.sub(r"\s+", " ", line).casefold()
        meaning = _PROGRAMMING_PHRASES.get(key) or _PROGRAMMING_GLOSSARY.get(key)
        if meaning is None and key.endswith("()"):
            # Empty-call spelling is allowed only for an exact known name, never
            # for decomposed identifiers or calls containing arguments.
            name = key[:-2]
            if re.fullmatch(r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*", name):
                meaning = _PROGRAMMING_PHRASES.get(name) or _PROGRAMMING_GLOSSARY.get(name)
        if meaning is None:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", line):
                return None
            parts = split_identifier(line)
            words = [part for part in parts if not part.isdigit()]
            if (not words or (len(parts) < 2 and not line.startswith("_"))
                    or any(part.lower() not in _PROGRAMMING_GLOSSARY for part in words)):
                return None
            meaning = " ".join(
                part if part.isdigit() else _PROGRAMMING_GLOSSARY[part.lower()]
                for part in parts
            )
        results.append(f"{line} = {meaning}")
    return "\n".join(results)



def _translate_word_batch(words: list[str], source: str, to: str) -> list[str]:
    """一次请求翻译多个单词（换行分隔），保持顺序与数量对齐。"""
    if not words:
        return []
    joined = "\n".join(words)
    out = _translate_youdao(joined, to, source)
    lines = [ln.strip() for ln in out.split("\n")]
    if len(lines) == len(words):
        return lines
    # 行数对不上时退化为逐个翻译
    result = []
    for w in words:
        try:
            result.append(_translate_youdao(w, to, source).strip().replace("\n", " "))
        except Exception:
            result.append("")
    return result


def explain_identifiers(
    text: str, source: str = "auto", target: str = "zh-Hans"
) -> list[str]:
    """对文本里的标识符做拆词翻译，返回每行 'ident = 词 词' 的说明。

    只用于程序员模式。翻译失败返回空列表，不影响主译文。
    """
    source = language_code(source)
    target = language_code(target)
    to = _target_lang(text, source, target)

    identifiers = find_identifiers(text)
    if not identifiers:
        return []

    # 收集所有不重复的词，一次性翻译，减少请求数
    vocab: list[str] = []
    index: dict[str, int] = {}
    for ident in identifiers:
        for part in split_identifier(ident):
            low = part.lower()
            if low in _STOPWORDS or low in index:
                continue
            index[low] = len(vocab)
            vocab.append(part)

    cached_vocab: list[str | None] = [None] * len(vocab)
    pending: list[str] = []
    pending_keys: list[str] = []

    # 1) 术语表优先：零延迟、语境准确
    for low, i in index.items():
        hit = (_PROGRAMMING_GLOSSARY.get(low)
               if to == "zh-Hans" and source in ("auto", "en") else None)
        if hit:
            cached_vocab[i] = hit

    # 2) 进程内缓存
    for low, i in index.items():
        if cached_vocab[i] is not None:
            continue
        hit = _cache_get(f"word:{low}", source, to, "vocab")
        if hit is not None:
            cached_vocab[i] = hit

    # 3) 剩余的词：优先免费接口（~150ms）；只有长文本才用 LLM
    for low, i in index.items():
        if cached_vocab[i] is None:
            pending.append(vocab[i])
            pending_keys.append(low)

    if pending:
        translated: list[str] = []
        use_llm_vocab = False
        try:
            from . import llm_translate

            use_llm_vocab = llm_translate.is_available() and len(text) >= _LLM_MIN_CHARS
        except Exception:
            use_llm_vocab = False

        if use_llm_vocab:
            try:
                from . import llm_translate

                mapping = llm_translate.translate_identifiers(pending, to)
                translated = [mapping.get(w, "") for w in pending]
            except Exception:
                translated = []
        if not translated or not any(translated):
            try:
                translated = _translate_word_batch(pending, source, to)
            except Exception:
                translated = []
        for low, val in zip(pending_keys, translated):
            idx = index.get(low)
            if idx is None:
                continue
            cached_vocab[idx] = val
            if val:
                _cache_put(f"word:{low}", source, to, "vocab", val)

    lines = []
    for ident in identifiers:
        parts = split_identifier(ident)
        translated_parts = []
        for part in parts:
            i = index.get(part.lower())
            translated_parts.append(cached_vocab[i] if i is not None and cached_vocab[i] else part)
        line = build_explanation(ident, translated_parts)
        if line:
            lines.append(line)
    return lines


# ---------------------------------------------------------------- 翻译缓存
_TRANSLATE_CACHE: dict[tuple[str, str, str, str], str] = {}
_CACHE_LIMIT = 512
_CACHE_LOCK = threading.RLock()


def _cache_get(text: str, source: str, to: str, mode: str) -> str | None:
    with _CACHE_LOCK:
        return _TRANSLATE_CACHE.get((text, source, to, mode))


def _cache_put(text: str, source: str, to: str, mode: str, result: str) -> None:
    with _CACHE_LOCK:
        if len(_TRANSLATE_CACHE) >= _CACHE_LIMIT:
            for key in list(_TRANSLATE_CACHE)[: _CACHE_LIMIT // 2]:
                _TRANSLATE_CACHE.pop(key, None)
        _TRANSLATE_CACHE[(text, source, to, mode)] = result


_LLM_TIMEOUT = 25.0   # 单次 LLM 调用上限（秒），与 llm_translate 内部超时一致
# 只有很长的文本才值得等 LLM（~1.7s）。免费接口 ~150ms 且质量够用。
# 实测：300 字仍是常见截图大小，会频繁触发 LLM 导致感知变慢。
_LLM_MIN_CHARS = 800
_FREE_TIMEOUT = 4.0   # 免费接口整体等待上限（原 9s，限流时白等太久）

# 熔断：某 provider 连续失败后短期跳过，避免每次都被限流拖满超时
_PROVIDER_FAIL_UNTIL: dict[str, float] = {}
_PROVIDER_COOLDOWN = 60.0


def _provider_alive(name: str) -> bool:
    return time.monotonic() >= _PROVIDER_FAIL_UNTIL.get(name, 0.0)


def _mark_provider_dead(name: str) -> None:
    _PROVIDER_FAIL_UNTIL[name] = time.monotonic() + _PROVIDER_COOLDOWN


def _llm_enabled() -> bool:
    try:
        from . import llm_translate

        return llm_translate.is_available()
    except Exception:
        return False


def _translate_with_llm(text: str, to: str, programmer: bool) -> str:
    from . import llm_translate

    return llm_translate.translate(text, to, programmer=programmer)


def translate(text: str, source: str = "auto", target: str = "zh-Hans", mode: str = "general") -> str:
    text = normalize_text(text, programmer_mode=mode == "programmer")
    if not text:
        return ""
    source = language_code(source)
    target = language_code(target)
    to = _target_lang(text, source, target)

    protected = {}
    request_text = text
    notes: list[str] = []

    # 缓存最优先：命中时完全不发网络请求（包括标识符拆词请求）
    cached = _cache_get(text, source, to, mode)
    if cached is not None:
        return cached

    if mode != "programmer":
        return _translate_general(text, source, target, to, mode)

    # ---------- 程序员模式 ----------
    if to == "zh-Hans" and source in ("auto", "en"):
        local = local_programming_translation(text)
        if local is not None:
            _cache_put(text, source, to, mode, local)
            return local

    # 纯标识符：只需拆词，不做整句翻译
    if _standalone_identifiers(text):
        notes = explain_identifiers(text, source, target)
        if notes:
            result = "\n".join(notes)
            _cache_put(text, source, to, mode, result)
            return result

    # 整句翻译与标识符拆词互不依赖，并行执行（约省一半耗时）
    # 短句优先免费接口（~150ms），长句才走 LLM（~2s，但语义更好）
    use_llm = _llm_enabled() and len(text) >= _LLM_MIN_CHARS
    box: dict[str, object] = {}

    def run_main():
        try:
            if use_llm:
                box["main"] = _translate_with_llm(text, to, True)
                return
            try:
                box["main"] = _translate_free(text, text, source, to, "programmer", [])
            except Exception:
                # 免费接口被限流：LLM 兜底
                if _llm_enabled():
                    box["main"] = _translate_with_llm(text, to, True)
                else:
                    raise
        except Exception:
            box["main"] = None

    def run_notes():
        try:
            box["notes"] = explain_identifiers(text, source, target)
        except Exception:
            box["notes"] = []

    t_main = threading.Thread(target=run_main, daemon=True)
    t_notes = threading.Thread(target=run_notes, daemon=True)
    t_main.start()
    t_notes.start()
    t_main.join(timeout=_LLM_TIMEOUT)
    t_notes.join(timeout=_LLM_TIMEOUT)

    notes = list(box.get("notes") or [])
    llm_out = box.get("main")

    if llm_out:
        merged = llm_out + ("\n\n" + "\n".join(notes) if notes else "")
        _cache_put(text, source, to, mode, merged)
        return merged

    # LLM 不可用/失败：走免费接口（占位符保护 + 兜底）
    if notes and _standalone_identifiers(text):
        result = "\n".join(notes)
        _cache_put(text, source, to, mode, result)
        return result

    request_text, protected = programmer_prepare(text)
    return _translate_free(request_text, text, source, to, mode, notes)


def _translate_general(text: str, source: str, target: str, to: str, mode: str) -> str:
    """普通模式：短文本走免费接口（快），长文本走 LLM（准）。

    免费接口被限流时，自动改用 LLM，避免直接报错。
    """
    prefer_llm = _llm_enabled() and len(text) >= _LLM_MIN_CHARS
    if prefer_llm:
        try:
            out = _translate_with_llm(text, to, False)
            if out:
                _cache_put(text, source, to, mode, out)
                return out
        except Exception:
            pass
    try:
        return _translate_free(text, text, source, to, mode, [])
    except Exception:
        if prefer_llm or not _llm_enabled():
            raise
        out = _translate_with_llm(text, to, False)   # 免费接口挂了，用 LLM 兜底
        if out:
            _cache_put(text, source, to, mode, out)
            return out
        raise


def _translate_free(request_text: str, original: str, source: str, to: str,
                    mode: str, notes: list[str]) -> str:
    """免费接口：有道 + Google 并行竞速。"""
    protected: dict[str, str] = {}
    if mode == "programmer":
        request_text, protected = programmer_prepare(original)

    import queue
    result_q: queue.Queue = queue.Queue()

    def run(fn):
        name = fn.__name__
        if not _provider_alive(name):
            result_q.put(("err", f"{name}: 冷却中"))
            return
        try:
            out = fn(request_text, to, source).strip()
            if out:
                _PROVIDER_FAIL_UNTIL.pop(name, None)   # 成功即恢复
                result_q.put(("ok", out))
            else:
                result_q.put(("err", f"{name}: empty"))
        except Exception as exc:
            # 限流/拒绝类错误：进入冷却，避免反复拖满超时
            msg = str(exc)
            if any(x in msg for x in ("429", "411", "403", "Too Many", "errorCode")):
                _mark_provider_dead(name)
            result_q.put(("err", f"{name}: {exc.__class__.__name__}: {msg[:80]}"))

    providers = [
        fn for fn in (_translate_youdao, _translate_google)
        if _provider_alive(fn.__name__)
    ]
    if not providers:
        raise RuntimeError("翻译接口全部处于限流冷却中，请稍后再试")

    threads = [
        threading.Thread(target=run, args=(fn,), daemon=True)
        for fn in providers
    ]
    for t in threads:
        t.start()

    errors = []
    deadline = time.monotonic() + _FREE_TIMEOUT
    for _ in range(len(threads)):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            errors.append("timeout")
            break
        try:
            kind, payload = result_q.get(timeout=remaining)
        except queue.Empty:
            errors.append("timeout")
            break

        if kind != "ok":
            errors.append(payload)
            continue

        result = restore_code_tokens(payload, protected) if protected else payload
        if protected and not validate_protected_tokens(result, protected):
            # 这个 provider 的 token 恢复不可靠，继续等另一个的结果
            errors.append("token 校验失败")
            continue

        if mode == "programmer" and notes and not _standalone_identifiers(original):
            result = result + "\n\n" + "\n".join(notes)
        _cache_put(original, source, to, mode, result)
        return result

    messages = "；".join(errors) if errors else "unknown"
    raise RuntimeError(f"翻译接口不可用（{messages}）")
