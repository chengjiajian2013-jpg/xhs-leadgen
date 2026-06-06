"""
AI 分析层 - LLM 三层过滤 + 话术生成

职责:
- 第一层: 判断帖子发帖人是买家还是卖家
- 第二层: 分析评论区确认发帖人身份
- 第三层: 生成个性化评论和私信话术
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("analyzer")

# 尝试导入 LLM 库
try:
    import requests as req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    """加载 prompt 模板文件"""
    path = PROMPTS_DIR / filename
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return f.read()
    logger.warning(f"Prompt 文件不存在: {path}")
    return ""


def _call_llm(system_prompt: str, user_message: str) -> Optional[str]:
    """
    调用 LLM API
    支持 OpenAI 兼容接口
    """
    from config import LLM_API_KEY, LLM_API_URL, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE

    api_key = LLM_API_KEY or os.environ.get("LLM_API_KEY", "")
    api_url = LLM_API_URL or os.environ.get("LLM_API_URL", "")

    if not api_key or not api_url:
        logger.warning("LLM API 未配置，跳过 AI 分析")
        return None

    if not HAS_REQUESTS:
        logger.warning("requests 库未安装，无法调用 LLM")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
        }

        # 如果是 Claude API (anthropic 格式)
        if "anthropic" in api_url.lower():
            payload = {
                "model": LLM_MODEL,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": LLM_MAX_TOKENS,
                "temperature": LLM_TEMPERATURE,
            }

        resp = req.post(api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # 兼容不同 API 返回格式
        if "choices" in data:
            content = data["choices"][0]["message"]["content"]
        elif "content" in data:
            content = data["content"]
        else:
            content = str(data)

        return content.strip()

    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return None


def _parse_json_from_llm(text: Optional[str]) -> Optional[dict]:
    """从 LLM 回复中提取 JSON"""
    if not text:
        return None

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试从文本中提取 {...}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法从 LLM 回复中解析 JSON: {text[:200]}")
    return None


# === 第一层: 帖子内容判断 ===

def judge_note(title: str, content: str) -> dict:
    """
    第一层判断: 分析帖子内容，判断发帖人角色

    返回:
    {
        "role": "buyer|seller|uncertain",
        "brand": "香奈儿|null",
        "specific_product": "CF黑金|null",
        "confidence": 0.95,
        "reasoning": "..."
    }
    """
    system_prompt = _load_prompt("judge_buyer.txt")
    if not system_prompt:
        return _default_judge_result()

    user_message = f"标题: {title}\n\n正文: {content}"
    response = _call_llm(system_prompt, user_message)
    result = _parse_json_from_llm(response)

    if result:
        return result

    return _default_judge_result()


def _default_judge_result() -> dict:
    """默认判断结果 - 不确定"""
    return {
        "role": "uncertain",
        "brand": None,
        "specific_product": None,
        "confidence": 0.0,
        "reasoning": "AI 分析不可用，跳过",
    }


# === 第二层: 评论区验证 ===

def judge_comments(note_title: str, note_author: str, comments: list[dict]) -> dict:
    """
    第二层判断: 通过评论区分析发帖人行为

    返回:
    {
        "role": "buyer|seller",
        "confidence": 0.9,
        "reasoning": "...",
        "seller_signals_found": []
    }
    """
    # 找到发帖人的回复
    author_replies = [
        c for c in comments
        if c.get("author", "") == note_author and c.get("is_reply", False)
    ]

    if not author_replies:
        # 没有发帖人的回复，说明评论区没有暴露信息，默认通过
        return {
            "role": "buyer",
            "confidence": 0.9,
            "reasoning": "发帖人在评论区没有回复，无卖家信号",
            "seller_signals_found": [],
        }

    system_prompt = _load_prompt("judge_comment.txt")
    if not system_prompt:
        return {"role": "buyer", "confidence": 0.8, "reasoning": "AI 不可用，默认通过", "seller_signals_found": []}

    # 整理发帖人的回复
    replies_text = "\n".join(
        f"- 回复 {c.get('reply_to', '未知')}: {c.get('text', '')}"
        for c in author_replies
    )

    user_message = f"帖子标题: {note_title}\n发帖人: {note_author}\n\n发帖人在评论区的回复:\n{replies_text}"
    response = _call_llm(system_prompt, user_message)
    result = _parse_json_from_llm(response)

    if result:
        return result

    return {"role": "buyer", "confidence": 0.8, "reasoning": "AI 分析失败，默认通过", "seller_signals_found": []}


# === 第三层: 话术生成 ===

def generate_reply(
    title: str,
    content: str,
    brand: Optional[str] = None,
    product: Optional[str] = None,
) -> dict:
    """
    第三层: 生成评论和私信话术

    返回:
    {
        "comment": "评论内容",
        "message": "私信内容"
    }
    """
    system_prompt = _load_prompt("generate_reply.txt")
    if not system_prompt:
        return _default_reply(brand, product)

    # 填充模板变量
    user_message = (
        f"帖子标题: {title}\n"
        f"帖子正文: {content}\n"
        f"提到的品牌: {brand or '未明确提及'}\n"
        f"提到的款式: {product or '未明确提及'}"
    )

    response = _call_llm(system_prompt, user_message)
    result = _parse_json_from_llm(response)

    if result and "comment" in result and "message" in result:
        return result

    return _default_reply(brand, product)


def _default_reply(brand: Optional[str], product: Optional[str]) -> dict:
    """默认话术（LLM 不可用时的降级方案）"""
    brand_str = brand or "大牌"
    product_str = f"（特别是{product}）" if product else ""

    return {
        "comment": f"{brand_str}确实经典{product_str}，我上海专柜有渠道能拿到正品折扣，比官网省不少～",
        "message": (
            f"看到你也在看{brand_str}{product_str}，我刚好有上海专柜的渠道，"
            f"保证正品还能拿到不错的折扣，感兴趣加🛰️聊聊？不买也可以先了解行情～"
        ),
    }
