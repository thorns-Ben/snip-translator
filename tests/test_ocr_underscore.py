"""OCR 下划线识别回归测试（渲染图，不依赖屏幕）。

    .venv/Scripts/python.exe test_ocr_underscore.py
"""

# --- 测试引导：确保能导入项目根目录模块 ---
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK，中文/符号输出会崩；统一成 UTF-8 并放宽错误
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from jietu import ocr_engine as oe

FONT = "C:/Windows/Fonts/msyh.ttc"
FAILED = []


def render(text, size=26, fg=(30, 30, 30), bg=(255, 255, 255)):
    f = ImageFont.truetype(FONT, size)
    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)
    b = d.textbbox((0, 0), text, font=f)
    img = Image.new("RGB", (b[2] - b[0] + 40, b[3] - b[1] + 40), bg)
    ImageDraw.Draw(img).text((20, 20), text, font=f, fill=fg)
    return img


VARIANTS = [
    ("light", 26, (30, 30, 30), (255, 255, 255)),
    ("dark", 26, (220, 220, 220), (40, 40, 40)),
    ("small", 13, (30, 30, 30), (255, 255, 255)),
]


def check(name, cond, detail=""):
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILED.append(name)


def main():
    oe.preload()

    # ---------------------------------------------------- 必须识别出下划线
    must = ["upload_file", "ocr_engine.py", "import_graph_state",
            "node_entry.py", "x1_y2"]
    for text in must:
        for label, size, fg, bg in VARIANTS:
            got = oe.recognize(render(text, size, fg, bg))
            check(f"下划线 {text} [{label}]", got == text, f"got {got!r}")

    # ---------------------------------------------------- 不能误加下划线
    plain = ["hello world", "the lazy dog", "world map", "ocr engine",
             "hello python", "Good morning"]
    for text in plain:
        for label, size, fg, bg in VARIANTS:
            got = oe.recognize(render(text, size, fg, bg))
            check(f"不应加下划线 {text} [{label}]",
                  "_" not in got, f"got {got!r}")

    # ---------------------------------------------------- 检测函数本身
    def crop_of(text, size=26, fg=(30, 30, 30), bg=(255, 255, 255)):
        import cv2
        img = render(text, size, fg, bg)
        arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        prepared = oe._prepare(arr)
        engine = oe.get_engine()
        boxes, _ = engine.text_det(prepared)
        ratio = arr.shape[1] / prepared.shape[1]
        ah, aw = arr.shape[:2]
        box = boxes[0]
        xs = [float(p[0]) * ratio for p in box]
        ys = [float(p[1]) * ratio for p in box]
        return arr[max(0, int(min(ys))):min(ah, int(max(ys)) + 1),
                   max(0, int(min(xs))):min(aw, int(max(xs)) + 1)]

    check("检测 upload_file 有 1 条", oe._find_underscores(crop_of("upload_file")) == 1,
          str(oe._find_underscores(crop_of("upload_file"))))
    check("检测 upload file 有 0 条", oe._find_underscores(crop_of("upload file")) == 0,
          str(oe._find_underscores(crop_of("upload file"))))
    check("检测 hello world 有 0 条", oe._find_underscores(crop_of("hello world")) == 0,
          str(oe._find_underscores(crop_of("hello world"))))
    check("检测 ocr engine 有 0 条", oe._find_underscores(crop_of("ocr engine")) == 0,
          str(oe._find_underscores(crop_of("ocr engine"))))

    # ---------------------------------------------------- 修复函数只在匹配时才改
    crop = crop_of("upload_file")
    check("fix: 空格数匹配时替换", oe._fix_baseline_chars("upload file", crop) == "upload_file")
    check("fix: 已有下划线不动", oe._fix_baseline_chars("upload_file", crop) == "upload_file")
    check("fix: 含中文不动", oe._fix_baseline_chars("上传 文件", crop) == "上传 文件")

    print("=" * 50)
    if FAILED:
        print(f"{len(FAILED)} 项失败")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
