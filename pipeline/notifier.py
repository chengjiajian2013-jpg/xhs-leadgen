"""
企业微信 Webhook 通知

职责:
- AI 确认买家后推送帖子信息到企业微信群机器人
- 包含标题、作者、品牌、置信度、链接、话术预览
"""
import json
import logging

logger = logging.getLogger("notifier")

try:
    import requests as req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def send_buyer_alert(
    webhook_url: str,
    title: str,
    author: str,
    brand: str,
    product: str,
    confidence: float,
    note_url: str,
    comment_text: str = "",
    message_text: str = "",
):
    """向企业微信群机器人推送一个确认的买家帖子"""
    if not HAS_REQUESTS:
        logger.warning("requests 未安装，无法推送企业微信")
        return False

    if not webhook_url:
        logger.warning("企业微信 Webhook URL 未配置")
        return False

    # 构建消息内容
    content_lines = [
        f"## 🔔 发现潜在买家",
        f"",
        f"**标题**: {title or '无标题'}",
        f"**作者**: {author or '未知'}",
        f"**品牌**: {brand or '未识别'}",
        f"**商品**: {product or '未识别'}",
        f"**置信度**: {confidence:.0%}",
        f"",
        f"**链接**: [查看帖子]({note_url})",
    ]

    if comment_text:
        content_lines.append(f"\n**评论话术**:\n{comment_text}")
    if message_text:
        content_lines.append(f"\n**私信话术**:\n{message_text}")

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(content_lines),
        },
    }

    try:
        resp = req.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info(f"企业微信推送成功: {title[:30]}...")
            return True
        else:
            logger.warning(f"企业微信推送返回错误: {result}")
            return False
    except Exception as e:
        logger.error(f"企业微信推送失败: {e}")
        return False


def send_startup_notice(webhook_url: str, demo_mode: bool, brands: list[str]):
    """发送系统启动通知"""
    if not HAS_REQUESTS or not webhook_url:
        return

    mode_str = "🧪 Demo 模式（仅推送，不操作）" if demo_mode else "🚀 完整模式"
    content = [
        f"## {mode_str}",
        f"",
        f"**监控品牌**: {', '.join(brands)}",
        f"**启动时间**: 系统已开始运行",
    ]

    try:
        req.post(webhook_url, json={
            "msgtype": "markdown",
            "markdown": {"content": "\n".join(content)},
        }, timeout=10)
    except Exception:
        pass
