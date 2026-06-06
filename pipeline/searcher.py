"""
搜索层 - 封装 opencli xiaohongshu search/note 调用

职责:
- 按关键词搜索小红书
- 读取笔记详情
- 读取笔记评论区
- 解析 JSON 输出
"""
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from config import (
    BRANDS_KEYWORDS,
    OPENCLI_CMD,
    OPENCLI_NODE,
    DEFAULT_PROFILE,
    SITE_SESSION,
    SEARCH_LIMIT,
    SEARCH_TIME_WINDOW_DAYS,
)

logger = logging.getLogger("searcher")

# Windows 下 .cmd 经由 cmd.exe 执行时会把 URL 中的 & 解释为命令分隔符，
# 导致 xsec_source= 后的部分被当成新命令。直接走 node 启动 main.js 绕过。
_is_windows = sys.platform == "win32"


def _run_opencli(args: list[str]) -> Optional[str]:
    """执行 opencli 命令，返回 stdout 字符串"""
    if _is_windows:
        cmd = OPENCLI_NODE + args
    else:
        cmd = [OPENCLI_CMD] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
        )
        # Windows 下解码：先 utf-8，失败则用 gbk
        stdout = result.stdout
        stderr = result.stderr

        if stdout:
            try:
                stdout = stdout.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    stdout = stdout.decode("gbk")
                except UnicodeDecodeError:
                    stdout = stdout.decode("gbk", errors="replace")

        if stderr:
            try:
                stderr = stderr.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    stderr = stderr.decode("gbk")
                except UnicodeDecodeError:
                    stderr = stderr.decode("gbk", errors="replace")

        if result.returncode != 0:
            stderr_text = stderr.strip() if stderr else ""
            logger.warning(f"opencli 命令失败: {' '.join(cmd[:6])}... | {stderr_text[:200]}")
            return None
        return stdout
    except subprocess.TimeoutExpired:
        logger.warning(f"opencli 命令超时: {' '.join(cmd[:6])}...")
        return None
    except FileNotFoundError:
        logger.error(f"opencli 未找到，请确认已安装: {OPENCLI_PATH}")
        return None


def _parse_json_output(output: Optional[str]) -> list[dict]:
    """解析 opencli 的 JSON 输出"""
    if not output:
        return []
    try:
        data = json.loads(output)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        logger.warning(f"JSON 解析失败，原始输出: {output[:200]}")
        return []


def search_notes(keyword: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """
    搜索小红书笔记

    返回格式:
    [
        {
            "rank": 1,
            "title": "笔记标题",
            "author": "作者名",
            "likes": "100",
            "published_at": "2026-06-01",
            "url": "https://www.xiaohongshu.com/..."   # 带 xsec_token
        }
    ]
    """
    output = _run_opencli([
        "xiaohongshu", "search", keyword,
        "--limit", str(limit),
        "-f", "json",
        "--site-session", SITE_SESSION,
    ])
    results = _parse_json_output(output)

    # 过滤近期的帖子
    if SEARCH_TIME_WINDOW_DAYS > 0:
        cutoff = (datetime.now() - timedelta(days=SEARCH_TIME_WINDOW_DAYS)).strftime("%Y-%m-%d")
        filtered = [r for r in results if r.get("published_at", "") >= cutoff]
        logger.info(f"搜索 '{keyword}': 共 {len(results)} 条，过滤后 {len(filtered)} 条")
        return filtered

    logger.info(f"搜索 '{keyword}': 共 {len(results)} 条")
    return results


def get_note_detail(note_url: str) -> Optional[dict]:
    """
    获取笔记详情

    返回格式: {field: value} 字典
    eg:
    {
        "title": "...",
        "author": "...",
        "content": "...",
        "likes": "100",
        "collects": "50",
        "comments": "20",
        "tags": "大牌,包包"
    }
    """
    output = _run_opencli([
        "xiaohongshu", "note", note_url,
        "-f", "json",
        "--site-session", SITE_SESSION,
    ])
    rows = _parse_json_output(output)
    if not rows:
        return None

    result = {}
    for row in rows:
        if isinstance(row, dict) and "field" in row and "value" in row:
            result[row["field"]] = row["value"]
    return result


def get_note_comments(note_url: str, limit: int = 30) -> list[dict]:
    """
    获取笔记评论

    返回格式:
    [
        {
            "rank": 1,
            "author": "评论者",
            "text": "评论内容",
            "likes": 5,
            "time": "2天前",
            "is_reply": false,
            "reply_to": ""
        }
    ]
    """
    output = _run_opencli([
        "xiaohongshu", "comments", note_url,
        "--limit", str(limit),
        "--with-replies",
        "-f", "json",
        "--site-session", SITE_SESSION,
    ])
    return _parse_json_output(output)


def get_all_search_results() -> dict[str, list[dict]]:
    """
    执行所有品牌+关键词的搜索，返回按品牌分组的搜索结果

    返回: {"香奈儿": [...], "Dior": [...], ...}
    """
    all_results = {}

    for brand, keywords in BRANDS_KEYWORDS.items():
        brand_notes = []
        seen_urls = set()

        for kw_entry in keywords:
            # 兼容 dict 格式（带 enabled 开关）和旧版字符串格式
            if isinstance(kw_entry, dict):
                if not kw_entry.get("enabled", True):
                    continue
                keyword = kw_entry["keyword"]
            else:
                keyword = kw_entry

            query = f"{brand} {keyword}"
            results = search_notes(query)

            for note in results:
                url = note.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    brand_notes.append(note)

            # 操作间隔，避免请求过快
            time.sleep(2)

        all_results[brand] = brand_notes
        logger.info(f"[{brand}] 搜索到 {len(brand_notes)} 条不重复帖子")

    return all_results


def extract_note_id(url: str) -> str:
    """从 URL 中提取笔记 ID"""
    match = re.search(r"/(?:explore|note|search_result)/([a-f0-9]{24})", url)
    if match:
        return match.group(1)
    return url


def convert_to_explore_url(url: str) -> str:
    """将 search_result URL 转换为 explore 格式（手机端可打开）"""
    note_id = extract_note_id(url)
    if not note_id:
        return url
    # 提取 xsec_token
    match = re.search(r"xsec_token=([^&]+)", url)
    token = match.group(1) if match else ""
    if token:
        return f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}"
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def extract_author_id_from_url(author_url: str) -> str:
    """从用户主页 URL 提取用户 ID"""
    match = re.search(r"/user/profile/([a-f0-9]+)", author_url)
    if match:
        return match.group(1)
    return author_url or ""
