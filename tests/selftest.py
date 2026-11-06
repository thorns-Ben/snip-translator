"""无 GUI 自检：生成一张含中英文的图，跑识别 + 翻译。"""

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

import time

from PIL import Image, ImageDraw, ImageFont

from jietu import ocr_engine


def make_test_image() -> Image.Image:
    img = Image.new("RGB", (760, 220), "white")
    d = ImageDraw.Draw(img)
    font_path = "C:/Windows/Fonts/msyh.ttc"
    big = ImageFont.truetype(font_path, 34)
    small = ImageFont.truetype(font_path, 28)
    d.text((30, 30), "人工智能正在改变世界", font=big, fill="black")
    d.text((30, 90), "The quick brown fox jumps over", font=small, fill="#111")
    d.text((30, 140), "the lazy dog. 这就是截图识别。", font=small, fill="#111")
    return img


def main():
    img = make_test_image()

    t = time.perf_counter()
    ocr_engine.preload()
    print(f"模型加载: {time.perf_counter() - t:.2f}s")

    t = time.perf_counter()
    text = ocr_engine.recognize(img)
    print(f"识别耗时: {time.perf_counter() - t:.3f}s")
    print("--- 识别结果 ---")
    print(text)
    print("----------------")

    assert "人工智能" in text, "中文识别失败"
    assert "quick brown" in text.replace("\n", " "), "英文识别失败"
    print("[OK] OCR")

    t = time.perf_counter()
    out = ocr_engine.translate("人工智能正在改变世界")
    print(f"翻译耗时: {time.perf_counter() - t:.2f}s")
    print("译文:", out)
    assert out.strip(), "翻译返回空"
    print("[OK] 翻译")


if __name__ == "__main__":
    main()
