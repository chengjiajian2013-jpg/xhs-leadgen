# xhs-leadgen · 小红书引流系统

> 基于 opencli 的自动化小红书引流工具 — 面向二奢行业（香奈儿/Dior/LV/卡地亚），AI 精准识别目标客户，自动完成关注→评论→私信引流闭环。

## 功能

- 🔍 定时搜索小红书：8 组关键词（4 品牌 × 2 关键词：额度/折扣）
- 🤖 AI 三层过滤：判断是真买家还是同行卖家
- 👤 自动关注 + AI 生成个性化评论（突出上海专柜正品折扣）
- 💬 延迟 2-6 小时后自动私信跟进，隐晦引导加 🛰️
- 👥 双账号支持，轮询操作分散风控
- 🛡 内置反风控策略：每日上限、随机延迟、操作时间窗口

## 依赖

- Python 3.11+
- [opencli](https://github.com/jackwener/opencli)（已全局安装）
- Chrome 浏览器（opencli daemon 使用）

## 快速开始

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 登录小红书账号
bash scripts/login.sh

# 3. 配置 LLM API（config.py 或环境变量）
export LLM_API_KEY="your-api-key"
export LLM_API_URL="https://api.openai.com/v1/chat/completions"

# 4. 启动（默认 Demo 模式：只推送企业微信，不执行真实互动）
python main.py
```

默认以 **Demo 模式**运行：AI 识别到买家后推送消息到企业微信群机器人，不执行关注/评论/私信。确认数据正常后，将 `config.py` 中 `DEMO_MODE = False` 开启完整模式。

## 配置

编辑 `config.py` 修改搜索关键词、操作频率、风控限制等。编辑 `accounts.json` 管理多账号。

详细配置说明见 [设计文档](docs/superpowers/specs/2026-06-06-xhs-leadgen-design.md)。

## 使用场景

本系统专为**二奢行业**设计：
- 在小红书上发现正在搜索/讨论奢侈品购买的用户
- AI 识别有真实购买意向的客户（过滤同行卖家）
- 以"上海专柜渠道、正品保障、折扣优惠"为卖点进行互动
- 安全隐晦地引导至微信私域完成转化

## 项目结构

```
├── main.py              # 主入口 + 调度器
├── config.py            # 配置管理
├── accounts.json        # 小红书账号配置
├── pipeline/
│   ├── searcher.py      # opencli 搜索封装
│   ├── analyzer.py      # AI 三层过滤 + 话术生成
│   ├── interactor.py    # 浏览器自动化操作
│   ├── notifier.py      # 企业微信推送
│   └── deduper.py       # SQLite 去重
├── db/                  # 数据库层
├── prompts/             # AI prompt 模板
└── scripts/
    └── login.sh         # 登录脚本
```

## 风控提醒

本系统会模拟真实用户行为，但请合理使用：
- 建议从低频（每 30 分钟）开始，观察几天后再提升
- 每天查看 `logs/` 下的操作日志
- 定期检查账号是否收到小红书风控通知
- 两个账号不要在同一 IP 下同时大量操作
