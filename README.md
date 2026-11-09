# 截图识字

Windows 截图 OCR + 翻译 + Snipaste 式标注 / 贴图，一个程序全包。

## 功能

### 识图翻译（Alt+D）
- **Alt+D** 框选区域识别翻译（主功能）
- **Alt+Q** 整屏识别
- **Alt+Z** 取词模式（光标周围）
- 选区可移动、可缩放，松手自动重新识别
- 结果面板贴选区上方，超出屏幕自动翻到下方
- 关闭方式：面板 ✕ / Esc / 点击选区外
- **代码模式**：保护标识符、路径、API 名，只翻译自然语言，并给出标识符拆词解释
- **中→英**：结果面板「中→英」按钮可把识别到的中文翻译成英文，再点一次恢复中文；可与代码模式同时使用
- **离线编程词库**：覆盖 Python、Java / Java SE、SQL、JavaScript 的关键字、标准 API、异常名和常用短语。中文目标、英文或自动源语言下，完整命中直接显示，无需网络；未知内容仍走在线翻译。
- 点号 API（如 `os.path.join`、`System.out.println`、`Promise.all`）、SQL 短语（如 `GROUP BY`）、已知名称的空参数写法（如 `json.loads()`）可匹配。带参数的调用和整段代码不会被当作短词硬替换；仅大小写与连续空白会被规范化。
- 词库统一维护在 `jietu/programming_glossary.py`。它是常用词集，不是完整的语言语法解析器；同名术语可能跨语言存在不同含义。

### 截图标注（F1，Snipaste 式）
- 框选后出现标注工具栏：矩形 / 椭圆 / 直线 / 箭头 / 画笔 / 荧光笔 / 文字 / 马赛克 / 模糊 / 橡皮擦 / 撤销重做 / 颜色 / 线宽
- **Ctrl+C** 复制图片、**Ctrl+S** 保存 PNG（程序目录的 `Screenshots` 文件夹）、**Enter / 双击** 复制并关闭
- **F3** 把当前选区贴到屏幕；**Esc** 退出，**右键** 先退工具再退出
- **C** 取色器：放大镜 + 像素网格 + HEX/RGB，左键复制色值
- **Tab** 窗口自动识别：悬停高亮窗口，左键采用为选区
- 方向键微移选区（Shift 加速），Ctrl+Z / Ctrl+Y 撤销重做
- 本模式**不会触发 OCR**

### 贴图（F3）
- 无截图时 F3 贴剪贴板图片；截图时 F3 贴当前选区
- 拖动移动、滚轮缩放、Ctrl+滚轮透明度
- 右键菜单：复制、另存为、旋转、翻转、不透明度、鼠标穿透、关闭全部
- 托盘「贴图」子菜单可统一显示 / 隐藏 / 关闭，并恢复鼠标穿透

> 若本机仍在运行 Snipaste，它会占用 F1 / F3。本程序会自动降级为 `Alt+1` / `Alt+3`（托盘菜单显示实际生效的键）；退出 Snipaste 后 F1 / F3 即可用。

## 安装

双击 `install.bat`（需要 Python 3.12）。

## 启动

### EXE 版（无需安装 Python）

解压发布 ZIP，保留整个 `截图识字` 文件夹，双击其中的 `截图识字.exe`。程序常驻系统托盘，没有常驻主窗口；不能只复制 EXE 而丢掉 `_internal` 依赖目录。

### 源码版

双击 `启动.bat`，或运行 `.venv\Scripts\python.exe -B run.py`。

### 开机自启动

托盘右键 → 勾选「开机自启动」。默认不自动开启，仅设置当前 Windows 用户，无需管理员权限；取消勾选即可关闭。启用前先把发布文件夹放到固定位置，移动或更换程序路径后需重新勾选。托盘原「整图转文本」入口已替换，Alt+Q 仍可整屏识别。

### 从源码构建 EXE

先运行 `install.bat`，再运行 `build_exe.bat`。构建使用 `requirements-build.txt` 和 `jietu.spec`；输出为 `dist\截图识字\截图识字.exe` 及依赖文件。Qt、OCR 模型和 ONNX Runtime 使发布包较大，这是正常情况。

启动错误与运行日志在 `%LOCALAPPDATA%\JietuScreenshot`，不写入 EXE 依赖目录。

## 保存与画质

- **Ctrl+S / 截图工具栏保存**：保存 PNG 到 EXE 所在目录的 `Screenshots` 子文件夹；源码运行时保存到项目根目录的 `Screenshots`，不使用当前工作目录或 C 盘图片目录。可在托盘选择「打开截图文件夹」，或通过 `JIETU_SAVE_DIR` 环境变量指定其他目录。
- **F3 贴图不会自动写文件**；退出后不保留。需要保留时，在贴图上右键「另存为」。
- PNG 是无损格式：文件压缩只减少体积，不降低像素质量。不必转成体积更大的 BMP，也不要转存 JPEG。
- 单屏选区从抓屏时保留的屏幕原始像素直接裁切，不使用预览缩放图；选区尺寸标签显示最终导出像素尺寸。没有标注的截图与原始裁切逐像素一致。
- 贴图滚轮缩放、透明度只改变屏幕显示，保存仍使用完整图像像素；标注、马赛克和模糊会按操作本身改变相应区域。
- 跨不同 DPI 屏幕的选区使用统一比例、最近邻合成，避免平滑插值；但不同屏幕的原生像素比例不同，跨屏成图并非各屏均为 1:1 原生像素。要求严格原生像素时，分别在各屏截图。
- 查看清晰度请用图片查看器的 100% 显示；「适应窗口」会缩放显示，不能用来判断文件是否丢失像素。屏幕截图保留的是屏幕上的像素，不能恢复原照片未显示出的细节。

## 大模型翻译（可选，推荐）

托盘右键 →「翻译设置」，可填写 API 请求地址、模型名和 API 密钥，勾选启用后保存。默认接口为现有智谱服务，其他服务需提供兼容的完整 chat/completions HTTPS 地址；模型名必须填写服务实际支持的名称。

- 密钥输入框默认遮挡，可切换显示；「测试连接」会发送一次小请求，可能产生服务方费用，操作在后台执行。
- 保存后之后的请求直接使用新设置，无需重启；取消不会保存。
- 配置位于 `%LOCALAPPDATA%\JietuScreenshot\settings.json`，密钥由 Windows DPAPI 按当前用户加密。复制到另一台电脑或另一用户后需重新输入密钥。
- 已保存的界面配置优先；尚未保存时读取 `ZHIPU_API_KEY` 环境变量，源码版还兼容根目录 `llm_config.py`。EXE 不包含该私有文件。
- 免费接口和本地词库仍保留。当前策略短内容优先免费接口/本地词库，较长内容可用大模型，接口失败时回退；填写模型并不代表每个短词都会发送给它。

未配置或关闭大模型不影响截图、OCR、本地词库与免费翻译。

OCR 在本机运行；在线翻译会把识别到的文字发送到对应翻译服务。F1 截图标注模式不触发 OCR 或翻译。

## 测试

```
run_tests.bat
```

或单独运行 `tests/` 下的脚本：

| 文件 | 内容 |
|---|---|
| `test_programmer.py` | 占位符保护、标识符拆词（不联网） |
| `test_ocr_underscore.py` | 下划线识别回归 |
| `selftest.py` | OCR + 翻译冒烟测试 |
| `apptest.py` | GUI 集成测试（托盘/热键/选区/翻译/标注/贴图） |
| `test_lossless.py` | 原始像素裁切、PNG 无损、DPI、贴图变换回归（不联网） |
| `test_autostart.py` | 自启动命令/注册表模拟测试，不修改真实启动项 |
| `test_settings.py` | 配置加密、优先级、设置界面与网络模拟测试 |
| `guitest.py` | 手动截图链路冒烟测试，不包含在批处理里 |
| `manual_e2e.py` | 手动真实识别翻译性能诊断，结果输出到控制台 |

`apptest.py` 会占用测试热键、修改剪贴板并模拟 F1/F3。运行前先从托盘退出常驻程序，避免热键冲突。高 DPI/多屏的自动测试使用合成数据，不等于已在各种多屏硬件上实测。

## 目录

```text
jietu/                   应用源码包
  __init__.py
  main.py                热键、托盘、OCR/翻译调度
  capture.py             框选内核、原生像素导出
  snip.py                标注/取色/输出会话
  annotations.py         标注模型与渲染
  toolbar.py             工具栏
  magnifier.py           取色放大镜
  window_detect.py       Win32 窗口识别
  pin_window.py          贴图窗口与管理器
  paths.py               保存路径与用户数据目录
  autostart.py           当前用户开机自启动
  settings.py            本地配置与 DPAPI 密钥加密
  settings_dialog.py     翻译设置窗口
  ocr_engine.py          OCR 与翻译
  programming_glossary.py 分类离线编程词库
  llm_translate.py       智谱后端
  result_window.py       整屏/取词结果窗
  hotkeys.py             Windows 全局热键
tests/                   自动测试及手动诊断
run.py                   统一启动入口
启动.bat                 无控制台启动
install.bat              安装依赖
run_tests.bat            自动测试入口
requirements.txt         运行依赖版本
requirements-build.txt   打包依赖版本
build_exe.bat            EXE 构建入口
jietu.spec               PyInstaller 构建配置
dist/                    本地发布产物，不提交源码仓库
llm_config.example.py    可公开的配置模板
llm_config.py            本地密钥，不提交
.venv/                   本地虚拟环境，不提交
```

## 上传 GitHub 前

- 上传源码包 `jietu/`、`tests/`、根目录启动/安装/测试脚本、`requirements.txt`、`README.md`、`.gitignore` 和 `llm_config.example.py`。
- **不上传** `llm_config.py`、`.venv/`、`.env`、`__pycache__/`、日志、临时截图和任何真实 API 密钥。这些本地内容由 `.gitignore` 排除；网页手动上传或压缩整个目录不会自动遵守 Git 忽略规则。
- 如果将来文件已经进入 Git 跟踪，新增忽略规则不会自动从历史中移除，提交前仍需检查暂存文件。
- 公开发布前自行选择适合项目的开源许可证；当前没有默认添加许可证。
- `build_exe.bat`、`requirements-build.txt` 和 `jietu.spec` 应提交，便于他人重建。EXE 发布文件夹和 ZIP 放 GitHub Releases，不要把大型构建输出当源码提交。
- 不上传本机 `%LOCALAPPDATA%\JietuScreenshot` 配置目录；即使密钥已加密也不是可公开的项目文件。
- 项目整理没有初始化仓库、提交或上传任何内容。

## 已知限制

- 多屏混合 DPI 的坐标换算未在真实高分屏环境验证
- 免费翻译接口对代码文本的语义理解有限，建议开启 LLM
- `a_b_c` 这类多个下划线的变量名偶有漏识别
- 窗口识别只到顶层窗口，暂不支持控件级（按钮/输入框）识别
- 贴图「鼠标穿透」后需从托盘菜单恢复
