"""程序员翻译模式的纯函数测试（不联网、不依赖 Qt）。

    .venv/Scripts/python.exe test_programmer.py
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

from jietu import ocr_engine as oe

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILED.append(name)


def roundtrip(text):
    prepared, protected = oe.programmer_prepare(text)
    return oe.restore_code_tokens(prepared, protected), protected


def main():
    # ---------------------------------------------------------- 保护与恢复
    code_cases = [
        "ImportGraphState is loaded from UploadFile.",
        r"The LangGraph API reads C:\work\src\main.py.",
        "Call graph.invoke({\"input\": text}) from ./src/main.py.",
        "import_graph_state and myURLParser and HTTPResponse",
        "POST /v1/runs/stream returns 200",
        "https://api.example.com/v1/runs with --dry-run",
        "Install pyside6>=6.7 and onnxruntime-directml",
        "Use `ImportGraphState` to init.",
        "def upload_file(path: str) -> UploadFile:",
        "\\\\server\\share\\file.py is remote",
        "路径是 D:\\项目\\main.py",
    ]
    for text in code_cases:
        restored, _ = roundtrip(text)
        check(f"roundtrip: {text[:44]}", restored == text, f"{restored!r} != {text!r}")

    # ---------------------------------------------------------- 关键 token 必须被保护
    must_protect = {
        "ImportGraphState is loaded from UploadFile.": ["ImportGraphState", "UploadFile"],
        "The LangGraph API reads the file.": ["LangGraph", "API"],
        r"Read C:\work\src\main.py now.": [r"C:\work\src\main.py"],
        "Use --dry-run please.": ["--dry-run"],
        "Check https://api.example.com/v1/runs": ["https://api.example.com/v1/runs"],
        "import_graph_state holds it": ["import_graph_state"],
    }
    for text, tokens in must_protect.items():
        _, protected = roundtrip(text)
        values = list(protected.values())
        for token in tokens:
            check(f"protect {token}", token in values, f"got {values}")

    # ---------------------------------------------------------- 普通英文不能被误保护
    for text in [
        "plain sentence with no code at all.",
        "Have a nice day.",
        "The quick brown fox jumps over the lazy dog.",
        "这是一个纯中文句子。",
    ]:
        _, protected = roundtrip(text)
        check(f"no false positive: {text[:36]}", not protected, f"got {list(protected.values())}")

    # ---------------------------------------------------------- 规范化
    check(
        "NFKC 全角转半角",
        oe.normalize_text("ＡＢＣ　１２３", programmer_mode=True) == "ABC 123",
    )
    check(
        "普通模式压缩空白",
        oe.normalize_text("a   b\n\n  c", programmer_mode=False) == "a b\n\nc",
    )
    check(
        "程序员模式保留缩进",
        oe.normalize_text("    def f():\n        pass", programmer_mode=True)
        == "    def f():\n        pass",
    )

    # ---------------------------------------------------------- 语言码
    check("语言映射 简体中文", oe.language_code("简体中文") == "zh-Hans")
    check("语言映射 英语", oe.language_code("英语") == "en")
    check("语言映射 自动", oe.language_code("自动") == "auto")
    check("有道 Auto->Auto 合法", oe._youdao_codes("auto", "zh-Hans") == ("Auto", "zh-CHS"))
    check("有道 中文源->en",
          oe._youdao_codes("zh-Hans", "en") == ("zh-CHS", "Auto"))

    # ---------------------------------------------------------- token 完整性校验（容忍个别丢失）
    protected = {"〔0〕": "ImportGraphState", "〔1〕": "UploadFile", "〔2〕": "API"}
    check("全部保留 -> 通过",
          oe.validate_protected_tokens("ImportGraphState UploadFile API", protected))
    check("丢 1 个仍通过（翻译器会吞占位符）",
          oe.validate_protected_tokens("ImportGraphState UploadFile", protected))
    check("丢 3 个才失败",
          not oe.validate_protected_tokens("nothing here", protected))

    # ---------------------------------------------------------- 占位符恢复
    prepped, real = oe.programmer_prepare("ImportGraphState and UploadFile")
    restored = oe.restore_code_tokens(prepped, real)
    check("占位符往返恢复", restored == "ImportGraphState and UploadFile", restored)

    # 译文里普通的 [2] / 【2】 不能被误当成占位符
    noisy = "结果[2]和【2】以及" + prepped
    restored_noisy = oe.restore_code_tokens(noisy, real)
    check("译文中的 [2] 不被误替换",
          "结果[2]和【2】" in restored_noisy, restored_noisy)
    check("同一次里 token 仍能恢复",
          "ImportGraphState" in restored_noisy and "UploadFile" in restored_noisy,
          restored_noisy)

    # ---------------------------------------------------------- 标识符拆词
    split_cases = {
        "current_number": ["current", "number"],
        "user_name": ["user", "name"],
        "ImportGraphState": ["Import", "Graph", "State"],
        "HTTPResponse": ["HTTP", "Response"],
        "currentNumber": ["current", "Number"],
        "file_path": ["file", "path"],
        "max_retries": ["max", "retries"],
    }
    for ident, expected in split_cases.items():
        got = oe.split_identifier(ident)
        check(f"拆词 {ident}", got == expected, f"{got} != {expected}")

    check("识别 snake_case 变量",
          "current_number" in oe.find_identifiers("use current_number here"),
          str(oe.find_identifiers("use current_number here")))
    check("识别 camelCase 变量",
          "currentNumber" in oe.find_identifiers("use currentNumber here"))
    check("短缩写不拆", oe.find_identifiers("call API now") == [])

    # 是否"只有标识符"
    check("current_number 判定为标识符为主",
          oe.is_identifier_dominated("current_number"))
    check("x = a_b + c_d 判定为标识符为主",
          oe.is_identifier_dominated("x = user_name + file_path"))
    check("自然语言不误判",
          not oe.is_identifier_dominated("hello world"))
    check("含标识符的句子不误判",
          not oe.is_identifier_dominated("The function upload_file writes to disk."))

    # 说明格式
    check("说明行格式",
          oe.build_explanation("current_number", ["当前的", "数量"])
          == "current_number = 当前的 数量")

    from unittest.mock import patch
    for text, expected in (("return", "返回"), ("ASYNC", "异步"),
                           ("middleware", "中间件"), ("connection refused", "连接被拒绝"),
                           ("getUserById", "根据 ID 获取用户"),
                           ("max_retry_count", "最大重试次数"),
                           ("HTTPResponse", "响应"), ("user_name", "用户名")):
        with patch.object(oe, "_translate_general", side_effect=AssertionError("unexpected network")), \
             patch.object(oe, "_translate_free", side_effect=AssertionError("unexpected network")), \
             patch.object(oe, "explain_identifiers", side_effect=AssertionError("unexpected fallback")):
            check(f"本地术语无需网络 {text}", expected in oe.translate(text, mode="programmer"))
    for text in ("The class is ready.", "unknownVariable", "returnValueUnknown", "classNameSuffix",
                 "return x + 1", "some ordinary English words"):
        check(f"不误匹配 {text}", oe.local_programming_translation(text) is None)
    with patch.object(oe, "_translate_general", return_value="general fallback"):
        check("普通模式不启用词典", oe.translate("middleware", mode="general") == "general fallback")
    with patch.object(oe, "_translate_free", return_value="English fallback"):
        check("英文目标不套用中文词典", oe.translate("return", target="en", mode="programmer") == "English fallback")

    # Expanded vocabulary: exercise every imported entry without network access.
    from jietu.programming_glossary import WORDS, PHRASES
    with patch.object(oe, "_translate_free", side_effect=AssertionError("unexpected network")), \
         patch.object(oe, "explain_identifiers", side_effect=AssertionError("unexpected notes")):
        for table, merged in ((WORDS, oe._PROGRAMMING_GLOSSARY),
                              (PHRASES, oe._PROGRAMMING_PHRASES)):
            for term in table:
                expected = f"{term} = {merged[term]}"
                check(f"expanded local {term}",
                      oe.translate(term, mode="programmer") == expected)

    api_cases = [
        "os.path.join", "pathlib.Path.read_text", "json.loads", "logging.getLogger",
        "dict.items", "asyncio.run", "FileNotFoundError", "ZeroDivisionError",
        "ModuleNotFoundError", "UnicodeDecodeError", "__init__", "__name__",
        "java.lang.RuntimeException", "java.util.concurrent.ExecutorService",
        "java.sql.PreparedStatement", "java.time.format.DateTimeFormatter",
        "System.out.println", "NullPointerException", "SQLException",
        "ConcurrentModificationException", "SELECT", "COALESCE", "CURRENT_TIMESTAMP",
        "Array.prototype.map", "Object.entries", "JSON.stringify", "Promise.allSettled",
        "document.querySelectorAll", "window.requestAnimationFrame", "URIError",
    ]
    with patch.object(oe, "_translate_free", side_effect=AssertionError("unexpected network")):
        for term in api_cases:
            exact = oe.local_programming_translation(term)
            folded = oe.local_programming_translation(term.swapcase())
            called = oe.local_programming_translation(term + "()")
            check(f"exact API/case/call {term}",
                  exact is not None and folded is not None and called is not None
                  and exact.split(" = ", 1)[1] == folded.split(" = ", 1)[1]
                  == called.split(" = ", 1)[1])
            check(f"API fastpath {term}", oe.translate(term, mode="programmer") == exact)
    for term in ("  GROUP\t BY  ", "public   static\tvoid main", "optional\tchaining"):
        check(f"phrase whitespace {term!r}", oe.local_programming_translation(term) is not None)
    for term in ("_file_path", "__user_name", "_user", "file2_path", "user_name42"):
        result = oe.local_programming_translation(term)
        check(f"known private/digits {term}", result is not None)
        if any(ch.isdigit() for ch in term):
            check(f"digits retained {term}", term[-2:] in result if term.endswith("42")
                  else "2" in result.split(" = ", 1)[1])
    for term in (
        "The class is ready.", "return value", "user name", "please return the file",
        "select the file", "group by user", "unknownThing", "_unknown_thing",
        "file2_unknown", "123", "___", "os.path.unknown", "user.name",
        "os . path . join", "json.loads(value)", "print(1)", "unknown_name()",
        "file_path()", "GROUP BY()", "json.loads ()", "json.loads() extra",
        "os.path.join;", "__unknown__", "returnValueUnknown", "_user_name = 2",
    ):
        check(f"strict local rejection {term}", oe.local_programming_translation(term) is None)
    check("legacy precise word retained", oe._PROGRAMMING_GLOSSARY["import"] == "导入")
    check("legacy precise phrase retained", oe._PROGRAMMING_PHRASES["unit test"].startswith("单元测试："))

    # Warm Chinese vocab cache, then ensure explicit source/target separation.
    oe._TRANSLATE_CACHE.clear()
    check("Chinese notes use glossary", oe.explain_identifiers("file_path") == ["file_path = 文件 路径"])
    oe._cache_put("word:file", "auto", "zh-Hans", "vocab", "中文缓存文件")
    oe._cache_put("word:path", "auto", "zh-Hans", "vocab", "中文缓存路径")
    for source, target in (("auto", "ja"), ("en", "ko"), ("auto", "en"),
                           ("ja", "zh-Hans"), ("ko", "zh-Hans")):
        with patch.object(oe, "_translate_word_batch",
                          side_effect=lambda words, src, dst: [dst + "-" + w for w in words]) as batch, \
             patch.object(oe, "_llm_enabled", return_value=False), \
             patch.object(oe, "_translate_free", return_value="provider-main"):
            notes = oe.explain_identifiers("file_path", source=source, target=target)
            check(f"notes language guard {source}->{target}",
                  notes == [f"file_path = {target}-file {target}-path"] and batch.called,
                  str(notes))
            result = oe.translate("file_path", source=source, target=target, mode="programmer")
            check(f"fallback no Chinese dictionary {source}->{target}",
                  result == notes[0] and not oe._CJK.search(result), result)
            check(f"exact API language guard {source}->{target}",
                  oe.translate("json.loads", source=source, target=target,
                               mode="programmer") == "provider-main")

    # High identifier coverage does not justify dropping executable syntax.
    for text in ("user_name, file_path", "user_name file_path", "user_name\nfile_path"):
        oe._TRANSLATE_CACHE.clear()
        with patch.object(oe, "_translate_free", side_effect=AssertionError("unexpected main")):
            check(f"standalone notes only {text!r}",
                  "file_path = 文件 路径" in oe.translate(text, mode="programmer"))
    for text in ("user_name = file_path", "user_name(file_path)",
                 "user_name + file_path", "user_name += file_path", "user_name == file_path"):
        oe._TRANSLATE_CACHE.clear()
        check(f"code not standalone {text}", not oe._standalone_identifiers(text))
        with patch.object(oe, "_llm_enabled", return_value=False), \
             patch.object(oe, "_translate_free", return_value=text) as main_translate:
            result = oe.translate(text, mode="programmer")
            check(f"code preserved with notes {text}",
                  result.startswith(text + "\n\n") and "file_path = 文件 路径" in result
                  and main_translate.called, result)
        # Exercise real protected-token restoration and final fallback notes.
        oe._TRANSLATE_CACHE.clear()
        with patch.object(oe, "_translate_youdao", new=lambda text, *args: text), \
             patch.object(oe, "_translate_google", new=lambda text, *args: text):
            result = oe._translate_free(text, text, "auto", "zh-Hans", "programmer",
                                        ["offline note"])
            check(f"protected code plus notes {text}", result == text + "\n\noffline note", result)
        oe._TRANSLATE_CACHE.clear()
        real_free = oe._translate_free
        attempts = []
        def fail_main_then_restore(*args):
            attempts.append(args)
            if len(attempts) == 1:
                raise RuntimeError("offline main failed")
            return real_free(*args)
        with patch.object(oe, "_llm_enabled", return_value=False), \
             patch.object(oe, "_translate_free", side_effect=fail_main_then_restore), \
             patch.object(oe, "_translate_youdao", new=lambda text, *args: text), \
             patch.object(oe, "_translate_google", new=lambda text, *args: text):
            result = oe.translate(text, mode="programmer")
            check(f"failed main retains code {text}",
                  len(attempts) == 2 and result.startswith(text + "\n\n"), result)

    print("=" * 50)
    if FAILED:
        print(f"{len(FAILED)} 项失败")
        return 1
    print("全部通过")
    return 0

if __name__ == "__main__":
    sys.exit(main())
