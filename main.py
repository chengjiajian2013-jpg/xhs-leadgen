"""
小红书引流系统 - 主入口 + APScheduler 调度器

调度流程:
1. 每10分钟执行一轮搜索
2. 定期检查 Phase2 (延迟私信) 任务
3. 定期检查 Phase3 (私信回复检查) 任务
"""
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 确保项目根目录在 Python 路径中
_root = Path(__file__).parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import (
    BRANDS_KEYWORDS,
    SEARCH_INTERVAL_MINUTES,
    BUYER_CONFIDENCE_THRESHOLD,
    OPERATE_HOUR_START,
    OPERATE_HOUR_END,
    LOG_DIR,
    LOG_LEVEL,
    PHASE2_DELAY_HOURS_MIN,
    PHASE2_DELAY_HOURS_MAX,
    PHASE3_DELAY_HOURS,
)
from db.connection import init_db
from pipeline.deduper import (
    is_note_processed,
    mark_note_skipped,
    mark_note_interested,
    get_pending_phase1,
    get_pending_phase2,
    get_pending_phase3,
    update_status,
    get_stats,
    get_daily_summary,
)
from pipeline.searcher import (
    get_all_search_results,
    get_note_detail,
    get_note_comments,
    extract_note_id,
)
from pipeline.analyzer import judge_note, judge_comments, generate_reply
from pipeline.interactor import (
    follow_author,
    comment_note,
    send_message,
    check_message_reply,
    close_browser_session,
)

# 日志设置
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(LOG_DIR) / f"leadgen_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("main")

# 账号轮询索引
_account_index = 0


def _load_accounts() -> list[dict]:
    """加载账号配置"""
    accounts_path = _root / "accounts.json"
    if accounts_path.exists():
        with open(accounts_path, encoding="utf-8") as f:
            return json.load(f)
    logger.warning("accounts.json 未找到，使用默认配置")
    return [{"name": "号1", "profile": "ucffv3fv", "is_primary": True}]


def _get_next_account() -> dict:
    """轮询获取下一个账号"""
    global _account_index
    accounts = _load_accounts()
    if not accounts:
        return {"name": "default", "profile": "ucffv3fv"}

    account = accounts[_account_index % len(accounts)]
    _account_index += 1
    return account


def _is_operating_hours() -> bool:
    """检查当前是否在操作时间窗口内"""
    now = datetime.now()
    hour = now.hour
    if OPERATE_HOUR_START <= OPERATE_HOUR_END:
        return OPERATE_HOUR_START <= hour < OPERATE_HOUR_END
    # 跨天情况（如 22:00 - 9:00）
    return hour >= OPERATE_HOUR_START or hour < OPERATE_HOUR_END


def _log_and_print_stats():
    """打印统计信息"""
    stats = get_stats()
    daily = get_daily_summary()

    logger.info("=" * 40)
    logger.info(f"系统统计: 共处理 {stats['total_processed']} 条帖子")
    logger.info(f"  - 识别为买家: {stats['buyers_identified']}")
    logger.info(f"  - 跳过卖家:   {stats['sellers_skipped']}")
    logger.info(f"  - Phase1 完成: {stats['phase1_completed']}")
    logger.info(f"  - Phase2 完成: {stats['phase2_completed']}")

    if daily:
        logger.info("今日用量:")
        for row in daily:
            logger.info(f"  [{row['account']}] {row['action']}: {row['count']}")
    logger.info("=" * 40)


# ============================================================
# 搜索 + 识别 Pipeline
# ============================================================

def _search_and_classify():
    """
    一轮搜索 + AI 识别流程:
    1. 搜索所有品牌关键词
    2. 去重过滤
    3. 读取笔记详情
    4. AI 第一层判断（内容分析）
    5. AI 第二层判断（评论验证）
    """
    if not _is_operating_hours():
        logger.info("当前不在操作时间窗口，跳过搜索")
        return

    # Step 1: 搜索
    logger.info("=" * 40)
    logger.info(f"开始第 {datetime.now().strftime('%H:%M:%S')} 轮搜索")
    logger.info("=" * 40)

    brand_results = get_all_search_results()
    total_new = 0

    # Step 2-5: 逐条处理
    for brand, notes in brand_results.items():
        for note in notes:
            note_url = note.get("url", "")
            note_id = extract_note_id(note_url)
            title = note.get("title", "")
            author = note.get("author", "")
            note_id_extracted = extract_note_id(note_url)

            if is_note_processed(note_url):
                continue

            total_new += 1
            logger.info(f"[{brand}] 分析新帖子: {title[:40]}...")

            # Step 3: 获取笔记详情
            note_detail = get_note_detail(note_url)
            if not note_detail:
                logger.warning(f"无法获取笔记详情，跳过: {note_url[:50]}")
                mark_note_skipped(note_url, title=title, author=author)
                continue

            note_content = note_detail.get("content", "")
            logger.info(f"  正文预览: {note_content[:80]}...")

            # Step 4: AI 第一层判断
            judgement = judge_note(title, note_content)
            logger.info(f"  第一层判断: role={judgement['role']}, "
                        f"confidence={judgement['confidence']:.2f}, "
                        f"brand={judgement.get('brand')}")

            if judgement["role"] != "buyer" or judgement["confidence"] < BUYER_CONFIDENCE_THRESHOLD:
                mark_note_skipped(
                    note_url,
                    title=title,
                    author=author,
                    brand=judgement.get("brand") or brand,
                    role=judgement["role"],
                    confidence=judgement["confidence"],
                )
                continue

            detected_brand = judgement.get("brand") or brand
            specific_product = judgement.get("specific_product")

            # Step 5: AI 第二层判断（评论区验证）
            logger.info(f"  执行第二层（评论区验证）...")
            comments = get_note_comments(note_url)
            comment_judgement = judge_comments(title, author, comments)
            logger.info(f"  第二层判断: role={comment_judgement['role']}, "
                        f"confidence={comment_judgement['confidence']:.2f}")

            if comment_judgement["role"] != "buyer":
                mark_note_skipped(
                    note_url,
                    title=title,
                    author=author,
                    brand=detected_brand,
                    role="seller",
                    confidence=comment_judgement["confidence"],
                )
                continue

            # 通过两层验证 → 标记为感兴趣
            record_id = mark_note_interested(
                note_url=note_url,
                title=title,
                author=author,
                author_id=note.get("author_url", ""),
                brand=detected_brand,
                confidence=min(judgement["confidence"], comment_judgement["confidence"]),
            )
            logger.info(f"  ✅ AI 确认买家! ID={record_id}, "
                        f"品牌={detected_brand}, 商品={specific_product}")

            # 控制处理速度
            time.sleep(3)

    logger.info(f"本轮搜索完成: 发现 {total_new} 条新帖子")


# ============================================================
# Phase1: 关注 + 评论
# ============================================================

def _process_phase1():
    """处理待执行的 Phase1 任务（关注+评论）"""
    if not _is_operating_hours():
        return

    pending = get_pending_phase1()
    if not pending:
        return

    logger.info(f"Phase1: 待处理 {len(pending)} 个任务")

    for note in pending:
        note_url = note["note_url"]
        note_id = note["id"]
        title = note.get("title", "")
        content = ""

        # 获取笔记详情用于话术生成
        detail = get_note_detail(note_url)
        if detail:
            content = detail.get("content", "")

        # 第三层：生成话术
        reply = generate_reply(
            title=title,
            content=content,
            brand=note.get("brand"),
        )

        # 分配账号
        account = _get_next_account()
        profile = account["profile"]
        account_name = account["name"]
        logger.info(f"Phase1 [{account_name}] 处理: {title[:40]}...")

        # 关注
        follow_success = follow_author(note_url, profile)
        time.sleep(random.uniform(2, 5))

        # 评论
        comment_text = reply.get("comment", "")
        comment_success = comment_note(note_url, comment_text, profile)
        time.sleep(random.uniform(2, 5))

        # 更新状态
        if follow_success and comment_success:
            update_status(
                note_id,
                "commented",
                account_used=profile,
                phase1_time=datetime.now(),
                comment_text=comment_text,
            )
            logger.info(f"✅ [{account_name}] Phase1 完成")
        elif follow_success:
            update_status(
                note_id,
                "followed",
                account_used=profile,
                phase1_time=datetime.now(),
            )
            logger.info(f"⚠️ [{account_name}] 已关注但评论失败")
        else:
            logger.warning(f"❌ [{account_name}] Phase1 失败")


# ============================================================
# Phase2: 私信
# ============================================================

def _process_phase2():
    """处理待执行的 Phase2 任务（私信）"""
    if not _is_operating_hours():
        return

    pending = get_pending_phase2()
    if not pending:
        return

    logger.info(f"Phase2: 检查待处理 {len(pending)} 个任务")

    now = datetime.now()

    for note in pending:
        note_id = note["id"]
        note_url = note["note_url"]
        phase1_time = note.get("phase1_time")

        if not phase1_time:
            continue

        # 解析时间
        if isinstance(phase1_time, str):
            phase1_time = datetime.fromisoformat(phase1_time)

        # 检查是否达到延迟时间
        delay_hours = random.uniform(PHASE2_DELAY_HOURS_MIN, PHASE2_DELAY_HOURS_MAX)
        min_delay = timedelta(hours=delay_hours)

        if now - phase1_time < min_delay:
            continue

        # 获取话术
        detail = get_note_detail(note_url)
        content = detail.get("content", "") if detail else ""
        reply = generate_reply(
            title=note.get("title", ""),
            content=content,
            brand=note.get("brand"),
        )
        message_text = reply.get("message", "")

        # 分配账号（尽量用和 Phase1 不同的号）
        account = _get_next_account()
        if account["profile"] == note.get("account_used"):
            # 如果同一个号，换另一个
            account = _get_next_account()
        profile = account["profile"]
        account_name = account["name"]

        logger.info(f"Phase2 [{account_name}] 发送私信给 {note['author']}...")

        success = send_message(note_url, note.get("author", ""), message_text, profile)

        if success:
            update_status(
                note_id,
                "messaged",
                account_used=profile,
                phase2_time=now,
                message_text=message_text,
            )
            logger.info(f"✅ [{account_name}] Phase2 私信完成")


# ============================================================
# Phase3: 检查私信回复
# ============================================================

def _process_phase3():
    """处理待执行的 Phase3 任务（检查回复）"""
    if not _is_operating_hours():
        return

    pending = get_pending_phase3()
    if not pending:
        return

    logger.info(f"Phase3: 检查待处理 {len(pending)} 个任务")

    now = datetime.now()

    for note in pending:
        note_id = note["id"]
        note_url = note["note_url"]
        phase2_time = note.get("phase2_time")

        if not phase2_time:
            continue

        if isinstance(phase2_time, str):
            phase2_time = datetime.fromisoformat(phase2_time)

        # 检查是否达到 24 小时
        if now - phase2_time < timedelta(hours=PHASE3_DELAY_HOURS):
            continue

        account_profile = note.get("account_used") or "ucffv3fv"
        logger.info(f"Phase3: 检查 {note['author']} 的回复...")

        reply = check_message_reply(note_url, note.get("author", ""), account_profile)

        if reply:
            logger.info(f"  {note['author']} 回复了: {reply[:80]}...")
            # 用户回复了，标记完成
            update_status(note_id, "converted", phase3_time=now)
            logger.info(f"✅ Phase3: {note['author']} 已回复，标记为转化")
        else:
            logger.info(f"  {note['author']} 未回复，标记完成")
            update_status(note_id, "no_reply", phase3_time=now)


# ============================================================
# 调度器
# ============================================================

def run_search_job():
    """搜索任务"""
    logger.info("启动搜索任务...")
    try:
        _search_and_classify()
    except Exception as e:
        logger.error(f"搜索任务异常: {e}", exc_info=True)


def run_interaction_job():
    """互动任务（Phase1 + Phase2 + Phase3）"""
    logger.info("启动互动任务...")
    try:
        _process_phase1()
        _process_phase2()
        _process_phase3()
    except Exception as e:
        logger.error(f"互动任务异常: {e}", exc_info=True)


def run_status_job():
    """状态报告任务"""
    _log_and_print_stats()


# ============================================================
# 主入口
# ============================================================

def main():
    """启动系统"""
    logger.info("=" * 50)
    logger.info("  小红书引流系统 启动")
    logger.info(f"  搜索间隔: {SEARCH_INTERVAL_MINUTES} 分钟")
    logger.info(f"  品牌: {', '.join(BRANDS_KEYWORDS.keys())}")
    logger.info(f"  操作时间: {OPERATE_HOUR_START}:00 - {OPERATE_HOUR_END}:00")
    logger.info("=" * 50)

    # 初始化数据库
    init_db()

    try:
        # 使用 APScheduler
        from apscheduler.schedulers.blocking import BlockingScheduler

        scheduler = BlockingScheduler(timezone="Asia/Shanghai")

        # 搜索任务（每10分钟）
        scheduler.add_job(
            run_search_job,
            "interval",
            minutes=SEARCH_INTERVAL_MINUTES,
            id="search",
            next_run_time=datetime.now(),
        )

        # 互动任务（每5分钟检查一次）
        scheduler.add_job(
            run_interaction_job,
            "interval",
            minutes=5,
            id="interact",
            next_run_time=datetime.now(),
        )

        # 状态报告（每30分钟）
        scheduler.add_job(
            run_status_job,
            "interval",
            minutes=30,
            id="status",
        )

        logger.info("调度器已启动，等待执行...")
        scheduler.start()

    except ImportError:
        # APScheduler 不可用，降级为手动循环
        logger.warning("APScheduler 未安装，使用简单循环模式")
        _simple_loop()
    except KeyboardInterrupt:
        logger.info("用户中断，正在退出...")
    finally:
        close_browser_session()
        from db.connection import close_db
        close_db()
        logger.info("系统已停止")


def _simple_loop():
    """简单循环模式（APScheduler 不可用时的降级方案）"""
    logger.info("进入简单循环模式")

    last_search_time = None
    last_status_time = None

    try:
        while True:
            now = datetime.now()

            # 搜索（每 SEARCH_INTERVAL_MINUTES 分钟）
            if not last_search_time or (now - last_search_time).total_seconds() >= SEARCH_INTERVAL_MINUTES * 60:
                run_search_job()
                last_search_time = now

            # 互动
            run_interaction_job()

            # 状态（每30分钟）
            if not last_status_time or (now - last_status_time).total_seconds() >= 1800:
                run_status_job()
                last_status_time = now

            # 休眠 60 秒后检查
            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("用户中断，正在退出...")


if __name__ == "__main__":
    main()
