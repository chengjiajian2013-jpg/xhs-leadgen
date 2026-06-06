# 小红书引流系统设计文档

## 概述

构建一套自动化的小红书引流系统，面向二奢行业（香奈儿、Dior、LV、卡地亚），基于 opencli 生态实现定时搜索、AI 识别真买家、自动关注+评论+私信的完整引流闭环，将目标用户导入微信私域。

## 核心业务逻辑

### 目标用户画像

- 在小红书上搜索/讨论奢侈品购买相关内容的用户
- 关键词：额度、折扣 + 品牌（香奈儿/Dior/LV/卡地亚）
- 行为特征：咨询购买、求推荐、比价、纠结是否入手

### 需要排除的对象

- 同行卖家（也在卖额度/折扣的账号）
- 广告号、营销号
- 纯分享无购买意向的用户

## 技术架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Scheduler (APScheduler)             │
│                      每 10 分钟触发一轮                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Main Pipeline                            │
│                                                              │
│  Step 1 ── 搜索层                                            │
│  opencli xiaohongshu search <关键词> -f json                   │
│  8组关键词 (4品牌 × 2关键词: 品牌+额度 / 品牌+折扣)             │
│                                                              │
│  Step 2 ── 去重层                                            │
│  SQLite 对比 note_url，过滤已处理/已跳过的帖子                    │
│                                                              │
│  Step 3 ── 内容读取层                                         │
│  opencli xiaohongshu note <url> -f json                      │
│  获取正文、作者、互动数据                                        │
│                                                              │
│  Step 4 ── AI 识别层 (3层过滤)                                 │
│  第一层: 帖子内容 → 判断发帖人是买家还是卖家                       │
│  第二层: 评论历史 → 该作者在其他帖子下的行为                       │
│  第三层: 话术匹配 → 按品牌+场景生成互动内容                       │
│                                                              │
│  Step 5 ── 互动层                                             │
│  opencli browser xhs 操作 Chrome 自动化                        │
│  Phase 1: 关注 + 评论 (立即)                                  │
│  Phase 2: 私信 (延迟2-6小时)                                  │
│                                                              │
│  Step 6 ── 记录层                                            │
│  SQLite 记录所有操作结果                                        │
└─────────────────────────────────────────────────────────────┘
```

### 组件选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 主控语言 | Python 3.11+ | LLM SDK 生态好，调度框架成熟 |
| 搜索&读取 | `opencli xiaohongshu` CLI | 通过 subprocess 调用，`-f json` 输出 |
| 浏览器自动化 | `opencli browser` | 与 opencli 共享 Chrome 登录态 |
| AI 识别+生成 | LLM API (Claude/GPT) | 判断购买意向 + 生成差异化话术 |
| 数据库 | SQLite | 轻量零配置，去重 + 操作记录 |
| 调度器 | APScheduler | 支持 Interval 定时触发 |

### 为什么选择纯 opencli 架构

1. **登录态统一**: opencli daemon 维护一个 Chrome Browser Bridge，`opencli xiaohongshu` 和 `opencli browser` 共享同一份 Cookie。一次 login 后所有操作都带着登录态
2. **零额外依赖**: 不需要 Playwright/Puppeteer/Selenium，opencli 自带的 browser 命令已覆盖 click/type/find/eval 等全部自动化操作
3. **适配器成熟**: xiaohongshu 适配器已实现 search/note/comments/login/whoami 等 20 个命令

## 数据流

### 搜索策略

每轮同时搜索 8 组关键词组合，每组取前 20 条结果：

| 品牌 | 关键词 1 | 关键词 2 |
|------|----------|----------|
| 香奈儿 | 香奈儿 额度 | 香奈儿 折扣 |
| Dior | Dior 额度 | Dior 折扣 |
| LV | LV 额度 | LV 折扣 |
| 卡地亚 | 卡地亚 额度 | 卡地亚 折扣 |

合并结果后按 note_id 去重，预估每轮获取 20-60 条新帖子。

### 帖子内容获取

搜索返回的 url 带 xsec_token，直接传给 note 命令读取详情：

```
opencli xiaohongshu note <url> -f json
→ {field: "title", value: "..."}
  {field: "content", value: "..."}
  {field: "author", value: "..."}
  {field: "likes", value: "..."}
  {field: "tags", value: "..."}
```

## AI 识别层设计

### 第一层：帖子内容判断

LLM 分析帖子的标题 + 正文，判断发帖人角色。

**真买家信号：**
- 咨询购买建议（"想买""求推荐""该不该入手"）
- 比价求建议（"哪里买划算""专柜还是代购"）
- 纠结款式（"选哪个""哪个颜色好看"）
- 求鉴别真伪
- 分享购买经历但带有咨询性质
- 预算讨论（"预算X万求推荐"）

**同行卖家信号：**
- 主动提供额度/折扣（"有额度""可带""私"）
- 报价/列价格表
- 大量晒货出货文案
- 直接留联系方式
- 同行间的互动（互关互赞）

**输出格式：**
```json
{
  "role": "buyer|seller|uncertain",
  "brand": "香奈儿|Dior|LV|卡地亚|null",
  "specific_product": "CF黑金|CarryAll|..." ,
  "confidence": 0.95,
  "reasoning": "用户提到想买香奈儿CF，纠结专柜价格"
}
```

仅当 `role == "buyer"` 且 `confidence >= 0.8` 时继续。

### 第二层：评论区行为验证

检查目标帖子的评论区，分析**发帖人在自己帖子评论区**的表现。

```
opencli xiaohongshu comments <note-url> -f json
```

有些卖家会伪装成买家发帖（标题正文像买家），但在评论区回复其他用户时暴露卖家身份（"我有额度""私我""滴滴"）。LLM 分析发帖人在评论区中的所有回复，如果表现出卖家行为则判定为同行并跳过，正常讨论则视为真买家。

### 第三层：话术生成

根据第一层提取到的品牌 + 具体款式 + 用户需求，生成个性化的评论和私信内容。

## 互动策略

### 阶梯式节奏

```
发现真买家帖子
       │
       ▼
Phase 1 ── 立即执行
  ├── 关注作者
  ├── 帖子下留评论 (AI 生成，自然语气)
  └── 评论示例: "CF黑金专柜确实难买，我们上海专柜有渠道
       能拿到正品折扣，比官网省不少～"
       │
       ▼  等待 2-6 小时
       │
Phase 2 ── 私信跟进 (延迟触发)
  ├── 打开作者主页 → 点击"私信"
  ├── 内容策略:
  │   先自然寒暄 → 给价值(上海专柜正品折扣) → 引导加微信
  ├── 私信示例:
  │   "看到你在看[品牌][款式]，我刚好有上海专柜的渠道，
  │    保证正品还能拿到不错的折扣，感兴趣加🛰️聊聊？
  │    不买也可以先了解行情～"
  └── 两个号轮流分配
       │
       ▼  等待 24 小时
       │
Phase 3 ── 转化确认 (可选)
  ├── 检查用户是否回复私信
  │   └── opencli browser xhs navigate 到私信列表页面
  │   └── opencli browser xhs extract 提取最新消息
  │   └── LLM 判断用户是否有回复 + 是否有意向
  ├── 已回复且有有意向 → 引导加🛰️
  └── 未回复/无意向 → 标记完成，不再跟进
```

### 品牌话术核心要素

| 要素 | 处理方式 |
|------|----------|
| 上海专柜渠道 | ✅ 明确突出 |
| 保证正品 | ✅ 明确突出 |
| 折扣优惠 | ✅ 明确突出 |
| 微信联系方式 | ❌ 用 🛰️ / V / 绿色软件 / 某信 替代 |
| "加微信" | ❌ 用"加个方式""交个朋友""细聊"替代 |

### 反风控策略

| 维度 | 策略 |
|------|------|
| 每号每日关注上限 | ≤30 人/天 |
| 每号每日评论上限 | ≤20 条/天 |
| 每号每日私信上限 | ≤15 条/天 |
| 单次操作间隔 | 30-90 秒随机 |
| 内容重复度 | AI 每次生成不同措辞 |
| 多号轮询 | 两个号交替使用 |
| 操作时间窗 | 仅 09:00-22:00 |
| 已处理记录 | SQLite 全量记录，绝不重复操作 |

## 数据库设计

### SQLite 表结构

```sql
-- 已处理帖子记录
CREATE TABLE processed_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_url TEXT UNIQUE NOT NULL,        -- 帖子 URL
    title TEXT,                           -- 标题
    author TEXT,                          -- 作者
    brand TEXT,                           -- 识别到的品牌
    role TEXT,                            -- buyer / seller / uncertain
    confidence REAL,                      -- AI 判断置信度
    status TEXT DEFAULT 'pending',        -- pending / interested / followed / commented / messaged / skipped
    -- pending: 新发现
    -- interested: AI 判断为买家
    -- followed: 已关注
    -- commented: 已评论
    -- messaged: 已私信
    -- skipped: AI 判断为卖家/不确定
    account_used TEXT,                    -- 操作的账号
    phase1_time TIMESTAMP,               -- Phase1 执行时间
    phase2_time TIMESTAMP,               -- Phase2 执行时间
    phase3_time TIMESTAMP,               -- Phase3 执行时间
    comment_text TEXT,                    -- 评论内容
    message_text TEXT,                    -- 私信内容
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 关键词配置
CREATE TABLE search_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,                  -- 品牌
    keyword TEXT NOT NULL,                -- 关键词（额度/折扣）
    active BOOLEAN DEFAULT TRUE
);

-- 操作日志
CREATE TABLE action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_url TEXT,
    action TEXT,                          -- follow / comment / message
    account TEXT,
    success BOOLEAN,
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 项目结构

```
D:/cjj/explorer/
├── main.py                    # 入口 + APScheduler 调度器
├── config.py                  # 配置管理（关键词、品牌话术、账号）
├── accounts.json              # 小红书账号配置
├── requirements.txt           # Python 依赖
│
├── pipeline/
│   ├── __init__.py
│   ├── searcher.py            # 调用 opencli search，解析结果
│   ├── analyzer.py            # LLM 判断层（3层过滤）
│   ├── interactor.py          # opencli browser 自动化操作
│   └── deduper.py             # SQLite 去重+记录
│
├── db/
│   ├── __init__.py
│   ├── connection.py          # SQLite 连接管理
│   └── schema.sql             # 建表 SQL
│
├── prompts/
│   ├── judge_buyer.txt        # AI 判断买家/卖家 prompt
│   ├── judge_comment.txt      # AI 评论历史分析 prompt
│   └── generate_reply.txt     # 话术生成 prompt
│
├── scripts/
│   └── login.sh               # 初始化登录脚本
│
├── logs/
│   └── ...                    # 运行时日志
│
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-06-06-xhs-leadgen-design.md
```

## 边界情况与错误处理

| 场景 | 处理方式 |
|------|----------|
| opencli 命令失败 | 重试 2 次，仍失败则跳过该帖子，记入 action_log |
| 小红书登录过期 | 检测到 AUTH_REQUIRED，暂停所有操作，提示重新 login |
| 网络/API 超时 | 跳过当前轮次，下一轮重试 |
| LLM API 调用失败 | 降级为 uncertain，跳过该帖子 |
| 搜索结果为空 | 正常跳过本轮，记录日志 |
| 风控限制（操作失败） | 降低该号操作频率，换号执行 |
| 重复帖子（同一内容不同 URL） | 按 note_id 去重，只处理一次 |
| 私信未回复 | Phase 3 检查后标记完成，不再跟进 |

## 安全与合规注意事项

1. ⚠️ 小红书反爬机制持续更新，操作频率需保守
2. ⚠️ 建议从低频开始运行（如每30分钟），观察一段时间无风控后再提升到10分钟
3. ⚠️ 两个账号不要在同 IP 下同时大量操作
4. ⚠️ 添加随机延时 + 随机鼠标轨迹模拟真人行为
5. ⚠️ 人工定期检查操作记录，及时发现异常

## 多账号管理

opencli daemon 关联单个 Chrome 配置文件（当前绑定 profile `ucffv3fv`），一个 Chrome 实例同时只能登录一个小红书号。两个号需要通过不同的 Chrome 配置文件实现隔离。

**推荐方案：Chrome 多 Profile 切换**

| 账号 | Chrome Profile | opencli --profile | 职责 |
|------|---------------|-------------------|------|
| 号1 | Default | `ucffv3fv` | 搜索 + 评论/私信主力 |
| 号2 | Profile 2 | 需新建并登录 | 分流操作，降低单号风控压力 |

在 opencli 中通过 `--profile <name>` 参数切换账号：

```
# 用号1操作
opencli --profile ucffv3fv xiaohongshu whoami

# 用号2操作（需要先在 Chrome Profile 2 中登录小红书）
opencli --profile profile2 xiaohongshu whoami
```

Python 调度层在执行操作前根据账号名选择对应的 profile，切换后自动继承对应账号的登录态。

## 扩展性预留

- **多账号支持**: accounts.json 已设计为数组，可扩展 N 个号
- **新品牌接入**: 只需在 config.py 中增加品牌+关键词配置
- **新平台扩展**: 搜索层抽象接口，后续可接入抖音/得物等
- **数据看板**: SQLite 数据可导出为报表，监控每日引流效果
