# 使用方式：
# 1. 复制本文件为同目录下的 user_settings.py
# 2. 在 user_settings.py 中填写下方变量（该文件已加入 .gitignore，勿提交仓库）
# 3. 若同时设置了环境变量 NARRATIVE_AI_*，仍以环境变量为准

# 必填（若未设置环境变量 NARRATIVE_AI_API_KEY）：OpenAI 兼容接口的密钥
NARRATIVE_AI_API_KEY = "sk-wzogtEZHkHfbIrxhgpmw2uQu9DaUNXnj0YNjGhJg8iU1PU8m"

# 可选：接口根地址（不要带 /v1/chat/completions）
NARRATIVE_AI_BASE_URL = "http://35.220.164.252:3888"

# 可选：模型名
NARRATIVE_AI_MODEL = "gpt-4o-mini"

# 可选：True 时不发网络请求，只返回占位文本
NARRATIVE_AI_DRY_RUN = False
