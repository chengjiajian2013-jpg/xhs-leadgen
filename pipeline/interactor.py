"""
互动层 - 通过 opencli browser 执行关注、评论、私信

职责:
- 关注作者
- 在帖子下评论
- 发送私信
- 检查私信回复

所有操作共享 opencli daemon 的 Chrome 登录态，不需要额外登录。
"""
import json
import logging
import random
import subprocess
import sys
import time
from typing import Optional

from config import (
    OPENCLI_CMD,
    OPENCLI_NODE,
    SITE_SESSION,
    BROWSER_WINDOW,
    BROWSER_SESSION_NAME,
    MIN_OPERATION_DELAY,
    MAX_OPERATION_DELAY,
    DAILY_LIMITS,
)
from pipeline.deduper import check_daily_limit, increment_daily_usage, log_action

logger = logging.getLogger("interactor")

_is_windows = sys.platform == "win32"


def _opencli_cmd(args: list[str]) -> list[str]:
    """构造 opencli 命令列表（兼容 Windows node 直启）"""
    if _is_windows:
        return OPENCLI_NODE + args
    return [OPENCLI_CMD] + args


def _browser(args: list[str], profile: str = "") -> Optional[str]:
    """执行 opencli browser 命令"""
    cmd = _opencli_cmd([])
    if profile:
        cmd += ["--profile", profile]
    cmd += ["browser", BROWSER_SESSION_NAME] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.warning(f"browser 命令失败: {args[:3]} | {stderr}")
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.warning(f"browser 命令超时: {args[:3]}")
        return None
    except FileNotFoundError:
        logger.error(f"opencli 命令失败: {OPENCLI_CMD}")
        return None


def _random_delay():
    """随机延迟，模拟真人操作"""
    delay = random.uniform(MIN_OPERATION_DELAY, MAX_OPERATION_DELAY)
    logger.debug(f"等待 {delay:.1f} 秒...")
    time.sleep(delay)


def _extract_json_from_output(output: Optional[str]):
    """从 browser 命令输出中提取 JSON（可能是 dict、str、list 等）"""
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _get_json_value(data, key: str, default=None):
    """安全地从可能是 dict 或非 dict 的 JSON 值中提取字段"""
    if isinstance(data, dict):
        return data.get(key, default)
    if isinstance(data, str):
        # 如果 data 本身就是字符串，当作结果返回
        return data
    return default


def _get_author_url_from_note(note_url: str, profile: str = "") -> Optional[str]:
    """
    从笔记页面获取作者主页 URL

    使用 opencli browser eval 从页面提取作者链接
    """
    _browser(["open", note_url, "--window", BROWSER_WINDOW], profile)
    time.sleep(3 + random.random() * 2)

    js = """
    (() => {
        const link = document.querySelector('a[href*="/user/profile/"]');
        if (!link) return null;
        const href = link.getAttribute('href');
        if (!href) return null;
        return href.startsWith('http') ? href : 'https://www.xiaohongshu.com' + href;
    })()
    """
    result = _browser(["eval", js], profile)
    data = _extract_json_from_output(result)
    href = _get_json_value(data, "_") if data else None
    return href if isinstance(href, str) and href else None


# === 关注操作 ===

def follow_author(note_url: str, account_profile: str) -> bool:
    """
    关注作者

    流程:
    1. 导航到笔记页面
    2. 查找作者信息
    3. 导航到作者主页
    4. 点击关注按钮
    """
    if not check_daily_limit(account_profile, "follow"):
        logger.warning(f"[{account_profile}] 关注已达每日上限")
        return False

    logger.info(f"[{account_profile}] 关注作者 (帖子: {note_url[:50]}...)")

    try:
        # Step 1: 导航到笔记页面
        _browser(["open", note_url, "--window", BROWSER_WINDOW], account_profile)
        time.sleep(3 + random.random() * 2)

        # Step 2: 查找并点击作者名进入主页
        # 先点击作者名跳转到作者主页
        click_result = _browser([
            "click", "--role", "link", "--name", "用户头像",
        ], account_profile)

        if not click_result:
            # 降级: 尝试通过 JS 获取作者链接
            js = """
            (() => {
                const link = document.querySelector('a[href*="/user/profile/"]');
                if (link) {
                    const url = link.getAttribute('href');
                    window.location.href = url.startsWith('/') ? 'https://www.xiaohongshu.com' + url : url;
                    return 'navigated';
                }
                return 'no_link_found';
            })()
            """
            _browser(["eval", js], account_profile)
            time.sleep(3 + random.random() * 2)

        # Step 3: 在作者主页点击关注
        _random_delay()
        result = _browser([
            "click", "--text", "关注",
        ], account_profile)

        success = result is not None
        log_action(note_url, "follow", account_profile, success)
        if success:
            increment_daily_usage(account_profile, "follow")
            logger.info(f"[{account_profile}] 关注成功")
        else:
            logger.warning(f"[{account_profile}] 关注失败")

        return success

    except Exception as e:
        logger.error(f"[{account_profile}] 关注操作异常: {e}")
        log_action(note_url, "follow", account_profile, False, str(e))
        return False


# === 评论操作 ===

def comment_note(note_url: str, text: str, account_profile: str) -> bool:
    """
    在帖子下评论

    流程:
    1. 导航到笔记页面
    2. 找到评论输入框
    3. 输入评论内容
    4. 发布
    """
    if not check_daily_limit(account_profile, "comment"):
        logger.warning(f"[{account_profile}] 评论已达每日上限")
        return False

    logger.info(f"[{account_profile}] 评论帖子")

    try:
        # Step 1: 导航到笔记页面
        _browser(["open", note_url, "--window", BROWSER_WINDOW], account_profile)
        time.sleep(3 + random.random() * 2)

        # Step 2: 滚动到评论区
        _browser(["eval", "window.scrollTo(0, document.body.scrollHeight * 0.6)"], account_profile)
        time.sleep(1 + random.random())

        # Step 3: 点击评论输入框
        _browser([
            "click", "--role", "textbox",
        ], account_profile)
        _random_delay()

        # Step 4: 输入评论内容
        _browser([
            "type", text,
        ], account_profile)
        time.sleep(1 + random.random())

        # Step 5: 发送/提交
        result = _browser([
            "keys", "Enter",
        ], account_profile)

        success = result is not None
        log_action(note_url, "comment", account_profile, success)
        if success:
            increment_daily_usage(account_profile, "comment")
            logger.info(f"[{account_profile}] 评论成功")
        else:
            logger.warning(f"[{account_profile}] 评论可能失败")

        return success

    except Exception as e:
        logger.error(f"[{account_profile}] 评论异常: {e}")
        log_action(note_url, "comment", account_profile, False, str(e))
        return False


# === 私信操作 ===

def send_message(note_url: str, author: str, text: str, account_profile: str) -> bool:
    """
    发送私信

    流程:
    1. 导航到作者主页
    2. 点击"私信"按钮
    3. 输入消息内容
    4. 发送
    """
    if not check_daily_limit(account_profile, "message"):
        logger.warning(f"[{account_profile}] 私信已达每日上限")
        return False

    logger.info(f"[{account_profile}] 发送私信给 {author}")

    try:
        # Step 1: 获取作者主页 URL
        author_url = _get_author_homepage(author, account_profile)
        if not author_url:
            # 从笔记页面提取
            _browser(["open", note_url, "--window", BROWSER_WINDOW], account_profile)
            time.sleep(2 + random.random())

            # 从页面提取作者链接并导航
            js = """
            (() => {
                const link = document.querySelector('a[href*="/user/profile/"]');
                return link ? link.getAttribute('href') : null;
            })()
            """
            result = _browser(["eval", js], account_profile)
            data = _extract_json_from_output(result)
            if data:
                href = _get_json_value(data, "_", "")
                if isinstance(href, str) and href and not href.startswith("http"):
                    href = "https://www.xiaohongshu.com" + href
                author_url = href if isinstance(href, str) and href else None

        if not author_url:
            logger.warning(f"[{account_profile}] 无法获取作者主页 URL")
            log_action(note_url, "message", account_profile, False, "无法获取作者主页")
            return False

        # Step 2: 导航到作者主页
        _browser(["open", author_url, "--window", BROWSER_WINDOW], account_profile)
        time.sleep(3 + random.random() * 2)

        # Step 3: 点击私信按钮
        result = _browser([
            "click", "--text", "私信",
        ], account_profile)

        if not result:
            logger.warning(f"[{account_profile}] 未找到私信按钮")
            log_action(note_url, "message", account_profile, False, "未找到私信按钮")
            return False

        time.sleep(2 + random.random())

        # Step 4: 输入消息
        _browser([
            "type", text,
        ], account_profile)
        _random_delay()

        # Step 5: 发送
        result = _browser([
            "keys", "Enter",
        ], account_profile)

        success = result is not None
        log_action(note_url, "message", account_profile, success)
        if success:
            increment_daily_usage(account_profile, "message")
            logger.info(f"[{account_profile}] 私信发送成功")
        else:
            logger.warning(f"[{account_profile}] 私信发送可能失败")

        return success

    except Exception as e:
        logger.error(f"[{account_profile}] 私信异常: {e}")
        log_action(note_url, "message", account_profile, False, str(e))
        return False


def _get_author_homepage(author_name: str, profile: str = "") -> Optional[str]:
    """通过搜索获取作者主页"""
    try:
        result = subprocess.run(
            _opencli_cmd(["xiaohongshu", "search", author_name, "-f", "json",
                          "--limit", "1", "--site-session", SITE_SESSION]),
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            if data and len(data) > 0:
                # search 结果没有 author_url，需要从 note 页面提取
                return None
    except Exception:
        pass
    return None


# === 检查私信回复 ===

def check_message_reply(note_url: str, author: str, account_profile: str) -> Optional[str]:
    """
    检查用户是否回复了私信

    返回: 用户的最新回复内容，如果没有回复则返回 None
    """
    logger.info(f"[{account_profile}] 检查 {author} 的私信回复")

    try:
        # 导航到私信列表
        _browser(["open", "https://www.xiaohongshu.com/notification", "--window", BROWSER_WINDOW], account_profile)
        time.sleep(3 + random.random() * 2)

        # 尝试切换到私信 tab
        # 实际需要看 XHS 私信页面的具体结构
        js = """
        (() => {
            // 尝试找到私信/消息区域的最新消息
            const messages = document.querySelectorAll('.msg-item, .message-item, [class*="chat"]');
            const lastMsg = messages[0];
            return lastMsg ? lastMsg.textContent.trim() : null;
        })()
        """
        result = _browser(["eval", js], account_profile)
        data = _extract_json_from_output(result)
        reply = _get_json_value(data, "_") if data else None

        log_action(note_url, "phase3_check", account_profile, True)
        return reply

    except Exception as e:
        logger.error(f"[{account_profile}] 检查私信回复异常: {e}")
        log_action(note_url, "phase3_check", account_profile, False, str(e))
        return None


# === 清理操作 ===

def close_browser_session():
    """关闭 browser session"""
    _browser(["close"])
    logger.info("浏览器 session 已关闭")
