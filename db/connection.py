"""
SQLite 数据库连接管理
"""
import sqlite3
import os
from pathlib import Path

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "leadgen.db"
SCHEMA_PATH = DB_DIR / "schema.sql"

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """获取数据库连接（单例模式）"""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(str(DB_PATH))
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


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
