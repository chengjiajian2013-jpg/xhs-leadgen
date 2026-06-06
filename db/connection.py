"""
SQLite 数据库连接管理
"""
import sqlite3
import threading
from pathlib import Path

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "leadgen.db"
SCHEMA_PATH = DB_DIR / "schema.sql"

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（每个线程独立连接）"""
    if not hasattr(_local, "connection") or _local.connection is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.connection = conn
    return _local.connection


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    if SCHEMA_PATH.exists():
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        print(f"[DB] 数据库初始化完成: {DB_PATH}")
    else:
        print(f"[DB] 警告: schema 文件不存在 {SCHEMA_PATH}")


def close_db():
    """关闭数据库连接"""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
