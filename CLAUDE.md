# xhs-leadgen — 小红书引流系统

## 项目概览

基于 opencli 生态的小红书自动引流系统。定时搜索指定品牌+关键词的新帖子，AI 三层过滤识别真买家，自动执行关注→评论→私信的阶梯式引流，将目标用户导入微信私域。

**二奢行业**：香奈儿、Dior、LV、卡地亚 — 上海专柜渠道、正品折扣。

## 架构速览

```
APScheduler (10min) → opencli search → LLM 三层过滤 → opencli browser 自动化
                         ↓                  ↓                   ↓
                    xiaohongshu search    buyer/seller judge    follow/comment/message
                    xiaohongshu note      评论区验证            同一 Chrome session
                    xiaohongshu comments  话术生成
```

详见 `docs/superpowers/specs/2026-06-06-xhs-leadgen-design.md`

## 边界规则 / 红线

- **LLM API Key 和 URL 从环境变量读取优先**：`LLM_API_KEY` / `LLM_API_URL`，config.py 里的空字符串只是占位
- **opencli 是唯一的外部依赖**：所有小红书操作（搜索、读取、关注、评论、私信）都走 opencli daemon，不用 Playwright/Puppeteer
- **登录态共享**：`opencli xiaohongshu` 和 `opencli browser` 共享同一个 Chrome Browser Bridge，一次 `login` 后不用二次登录
- **双账号隔离**：通过 `opencli --profile` 切换 Chrome 用户配置文件实现多账号，不是在一个 Chrome 实例里切 Cookie
- **操作时间窗口**：09:00-22:00，其余时间不执行
- **反风控守则**：关注 ≤30/天/号，评论 ≤20/天/号，私信 ≤15/天/号，间隔 30-90s 随机
- **话术红线**：突出"上海专柜""正品"，但用 🛰️ 替代"微信"
- **APScheduler 非必需**：未安装时自动降级为 60s 轮询简单循环

## 命令速查

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py

# 登录（首次）
bash scripts/login.sh                  # 号1 (profile: ucffv3fv)
opencli --profile profile2 xiaohongshu login --site-session persistent  # 号2

# 验证登录
opencli --profile ucffv3fv xiaohongshu whoami -f yaml

# 手动测试搜索
opencli xiaohongshu search "香奈儿 折扣" --limit 5 -f json --site-session persistent
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | config.py 中配置 |
| `LLM_API_URL` | LLM API 端点 | config.py 中配置 |

## 深入文档指针

| 主题 | 位置 |
|------|------|
| 完整设计文档 | `docs/superpowers/specs/2026-06-06-xhs-leadgen-design.md` |
| 搜索配置 | `config.py` — BRANDS_KEYWORDS |
| AI 判断逻辑 | `prompts/judge_buyer.txt`, `prompts/judge_comment.txt` |
| 话术模板 | `prompts/generate_reply.txt` |
| DB 方案 | `db/schema.sql` |
| 账号配置 | `accounts.json` |
| GitHub | https://github.com/chengjiajian2013-jpg/xhs-leadgen |
