# 智谱 AI 配置
# 复制本文件为 llm_config.py 并填入你的 key。
# 也可以直接设置环境变量 ZHIPU_API_KEY，优先于本文件。

ZHIPU_API_KEY = ""
ZHIPU_MODEL = "glm-4-flash"
# 是否启用大模型翻译（True 时优先用 LLM，失败自动回退到免费接口）
USE_LLM_TRANSLATION = True
