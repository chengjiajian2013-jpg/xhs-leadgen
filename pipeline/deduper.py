"""
SQLite 去重 + 操作记录层

职责:
- 检查帖子是否已处理过
- 记录帖子处理状态
- 记录操作日志
- 管理每日用量统计
"""
import json
from datetime import date, datetime
from typing import Optional

from db.connection import get_connection


def is_note_processed(note_url: str) -> bool:
    """检查帖子是否已处理过"""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM processed_notes WHERE note_url = ?",
        (note_url,),
    ).fetchone()
    return row is not None


def mark_note_skipped(
    note_url: str,
    title: str = "",
    author: str = "",
    brand: str = "",
    role: str = "uncertain",
    confidence: float = 0.0,
):
    """标记帖子为跳过（卖家/不确定）"""
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO processed_notes
           (note_url, title, author, brand, role, confidence, status)
           VALUES (?, ?, ?, ?, ?, ?, 'skipped')""",
        (note_url, title, author, brand, role, confidence),
    )
    conn.commit()


def mark_note_interested(
    note_url: str,
    title: str = "",
    author: str = "",
    author_id: str = "",
    brand: str = "",
    confidence: float = 0.0,
) -> int:
    """标记帖子为有兴趣的买家，返回记录 ID"""
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO processed_notes
           (note_url, title, author, author_id, brand, role, confidence, status)
           VALUES (?, ?, ?, ?, ?, 'buyer', ?, 'interested')""",
        (note_url, title, author, author_id, brand, confidence),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM processed_notes WHERE note_url = ?",
        (note_url,),
    ).fetchone()
    return row["id"] if row else 0


def get_pending_phase1() -> list[dict]:
    """获取待执行 Phase1 的帖子"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM processed_notes WHERE status = 'interested' ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_phase2() -> list[dict]:
    """获取待执行 Phase2 的帖子（已评论但未私信，且超过延迟时间）"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM processed_notes
           WHERE status = 'commented'
           AND phase1_time IS NOT NULL
           ORDER BY phase1_time ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_phase3() -> list[dict]:
    """获取待执行 Phase3 的帖子（已私信但未检查回复）"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM processed_notes
           WHERE status = 'messaged'
           AND phase2_time IS NOT NULL
           ORDER BY phase2_time ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def update_status(note_id: int, status: str, **extra_fields):
    """更新帖子状态和额外字段"""
    conn = get_connection()
    fields = {"status": status, "updated_at": datetime.now()}
    fields.update(extra_fields)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [note_id]

    conn.execute(
        f"UPDATE processed_notes SET {set_clause} WHERE id = ?",
        values,
    )
    conn.commit()


def log_action(
    note_url: str,
    action: str,
    account: str,
    success: bool,
    error_msg: str = "",
):
    """记录操作日志"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO action_log (note_url, action, account, success, error_msg)
           VALUES (?, ?, ?, ?, ?)""",
        (note_url, action, account, success, error_msg),
    )
    conn.commit()


def check_daily_limit(account: str, action: str) -> bool:
    """检查某账号某操作是否已达每日上限"""
    from config import DAILY_LIMITS

    limit = DAILY_LIMITS.get(action, 999)
    today = date.today().isoformat()
    conn = get_connection()
    row = conn.execute(
        """SELECT count FROM daily_usage
           WHERE date = ? AND account = ? AND action = ?""",
        (today, account, action),
    ).fetchone()
    current = row["count"] if row else 0
    return current < limit


def increment_daily_usage(account: str, action: str):
    """增加每日用量计数"""
    today = date.today().isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO daily_usage (date, account, action, count)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(date, account, action)
           DO UPDATE SET count = count + 1""",
        (today, account, action),
    )
    conn.commit()


def get_daily_summary() -> list[dict]:
    """获取每日操作汇总"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT date, account, action, count
           FROM daily_usage
           ORDER BY date DESC, account, action
           LIMIT 50"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """获取系统统计"""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM processed_notes").fetchone()["c"]
    buyers = conn.execute(
        "SELECT COUNT(*) as c FROM processed_notes WHERE role = 'buyer'"
    ).fetchone()["c"]
    sellers = conn.execute(
        "SELECT COUNT(*) as c FROM processed_notes WHERE role = 'seller'"
    ).fetchone()["c"]
    phase1_done = conn.execute(
        "SELECT COUNT(*) as c FROM processed_notes WHERE status IN ('followed','commented')"
    ).fetchone()["c"]
    phase2_done = conn.execute(
        "SELECT COUNT(*) as c FROM processed_notes WHERE status = 'messaged'"
    ).fetchone()["c"]

    return {
        "total_processed": total,
        "buyers_identified": buyers,
        "sellers_skipped": sellers,
        "phase1_completed": phase1_done,
        "phase2_completed": phase2_done,
    }
