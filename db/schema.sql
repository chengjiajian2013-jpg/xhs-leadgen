-- 小红书引流系统 - 数据库表结构

-- 已处理帖子记录
CREATE TABLE IF NOT EXISTS processed_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_url TEXT UNIQUE NOT NULL,        -- 帖子 URL
    title TEXT,                           -- 标题
    author TEXT,                          -- 作者
    author_id TEXT,                       -- 作者用户 ID
    brand TEXT,                           -- 识别到的品牌
    role TEXT,                            -- buyer / seller / uncertain
    confidence REAL,                      -- AI 判断置信度
    status TEXT DEFAULT 'pending',        -- pending / interested / followed / commented / messaged / skipped
    account_used TEXT,                    -- 操作的账号 profile
    phase1_time TIMESTAMP,               -- Phase1 执行时间
    phase2_time TIMESTAMP,               -- Phase2 执行时间
    phase3_time TIMESTAMP,               -- Phase3 执行时间
    comment_text TEXT,                    -- 评论内容
    message_text TEXT,                    -- 私信内容
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 操作日志
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_url TEXT,
    action TEXT,                          -- search / follow / comment / message / phase3_check
    account TEXT,
    success BOOLEAN,
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 每日用量统计
CREATE TABLE IF NOT EXISTS daily_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                   -- YYYY-MM-DD
    account TEXT NOT NULL,
    action TEXT NOT NULL,                 -- follow / comment / message
    count INTEGER DEFAULT 0,
    UNIQUE(date, account, action)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_notes_status ON processed_notes(status);
CREATE INDEX IF NOT EXISTS idx_notes_created ON processed_notes(created_at);
CREATE INDEX IF NOT EXISTS idx_action_log_created ON action_log(created_at);
CREATE INDEX IF NOT EXISTS idx_daily_usage_date ON daily_usage(date);
