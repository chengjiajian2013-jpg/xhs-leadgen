# 小红书引流系统 - 配置

# === 品牌与搜索关键词 ===
# 每轮搜索的组合：每个品牌下可启用/禁用特定关键词
# enabled: true 表示该关键词生效，false 表示跳过
BRANDS_KEYWORDS = {
    "香奈儿": [
        {"keyword": "额度", "enabled": True},
        {"keyword": "折扣", "enabled": True},
        {"keyword": "全新", "enabled": True},
        {"keyword": "刚抱出", "enabled": True},
    ],
    "Dior": [
        {"keyword": "额度", "enabled": True},
        {"keyword": "折扣", "enabled": True},
        {"keyword": "全新", "enabled": True},
        {"keyword": "刚抱出", "enabled": True},
    ],
    "LV": [
        {"keyword": "额度", "enabled": True},
        {"keyword": "折扣", "enabled": True},
        {"keyword": "全新", "enabled": True},
        {"keyword": "刚抱出", "enabled": True},
    ],
    "卡地亚": [
        {"keyword": "额度", "enabled": True},
        {"keyword": "折扣", "enabled": True},
        {"keyword": "全新", "enabled": True},
        {"keyword": "刚抱出", "enabled": True},
    ],
}

# === 搜索参数 ===
SEARCH_LIMIT = 20          # 每组关键词取前 N 条
SEARCH_INTERVAL_MINUTES = 10  # 每轮间隔（分钟）
SEARCH_TIME_WINDOW_DAYS = 7   # 只看近 N 天的帖子

# === AI 判断阈值 ===
BUYER_CONFIDENCE_THRESHOLD = 0.8  # 判定为买家的最小置信度

# === 反风控限制 (每日上限, 每号) ===
DAILY_LIMITS = {
    "follow": 30,
    "comment": 20,
    "message": 15,
}

# === 操作时间窗口 ===
OPERATE_HOUR_START = 9    # 开始操作时间 (24h)
OPERATE_HOUR_END = 22     # 结束操作时间 (24h)

# === 操作延迟 (秒) ===
MIN_OPERATION_DELAY = 30   # 单次操作最小间隔
MAX_OPERATION_DELAY = 90   # 单次操作最大间隔

# === Phase 延迟 ===
PHASE2_DELAY_HOURS_MIN = 2   # Phase1 → Phase2 最小等待
PHASE2_DELAY_HOURS_MAX = 6   # Phase1 → Phase2 最大等待
PHASE3_DELAY_HOURS = 24      # Phase2 → Phase3 等待

# === LLM API 配置 ===
LLM_API_URL = "https://api.deepseek.com/chat/completions"  # DeepSeek API 地址
LLM_API_KEY = "sk-2953468f14f0462791cc456ee7f60baf"          # API Key (从环境变量读取优先)
LLM_MODEL = "deepseek-chat"       # 模型名 (deepseek-chat = V4 Flash)
LLM_MAX_TOKENS = 1024
LLM_TEMPERATURE = 0.7

# === opencli 配置 ===
OPENCLI_CMD = "opencli.cmd"    # Windows 下 .cmd 包装器，subprocess 会自动用 cmd.exe 执行
# 用 node 直接执行 opencli 的主 js，避免 .cmd 经由 cmd.exe 时 &
# 把 URL 参数里的 & 解释为命令分隔符
OPENCLI_NODE = [
    "node",
    r"C:\Users\Netis\AppData\Roaming\npm\node_modules\@jackwener\opencli\dist\src\main.js",
]
DEFAULT_PROFILE = "ucffv3fv"  # 默认 Chrome profile (号1)
SITE_SESSION = "persistent"   # session 模式
BROWSER_WINDOW = "background" # 浏览器窗口模式
BROWSER_SESSION_NAME = "xhs_leadgen"  # opencli browser session 名称

# === 日志 ===
LOG_DIR = "logs"
LOG_LEVEL = "INFO"

# === Demo 模式 ===
# True: 只搜索 + AI 识别，识别到买家后推送到企业微信，不执行关注/评论/私信
# False: 完整模式，执行关注/评论/私信
DEMO_MODE = True

# === 企业微信 Webhook（Demo 模式推送用）===
WEWORK_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=c2138987-b9a1-49be-9b99-2f9c48ca2d20"
