"""Scheduler for automatic daily content generation."""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    DAILY_GENERATION_HOUR_UTC,
    DAILY_GENERATION_MINUTE,
    TELEGRAM_ADMIN_IDS,
    PRODUCTS_TO_SELECT_DAILY,
)
from database import models
from services import cscart, claude_stylist, klingai

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot = None


def init_scheduler(bot):
    """Initialize the scheduler with the bot instance."""
    global _scheduler, _bot
    _bot = bot

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        daily_generation_job,
        CronTrigger(hour=DAILY_GENERATION_HOUR_UTC, minute=DAILY_GENERATION_MINUTE),
        id="daily_generation",
        name="Daily video content generation",
        replace_existing=True,
    )
    logger.info(
        f"Scheduler configured: daily at {DAILY_GENERATION_HOUR_UTC:02d}:"
        f"{DAILY_GENERATION_MINUTE:02d} UTC"
    )


def start_scheduler():
    """Start the scheduler."""
    if _scheduler:
        _scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler gracefully."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


async def _notify_admins(text: str):
    """Send a notification message to all admin users."""
    if not _bot:
        logger.warning("Bot not available for notifications")
        return
    for admin_id in TELEGRAM_ADMIN_IDS:
        try:
            await _bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def daily_generation_job():
    """Run the daily content generation pipeline.

    This is the main scheduled job that:
    1. Fetches products from CS-Cart
    2. Scores and selects via Claude AI
    3. Generates prompts
    4. Creates KlingAI video tasks
    5. Polls for results and notifies admins
    """
    logger.info("=== Daily generation job started ===")
    session_id = await models.create_session()

    try:
        # Step 1: Fetch products
        await _notify_admins("🚀 Запускаю ежедневную генерацию контента...")

        new_products = await cscart.get_new_products(days=7, limit=15)
        popular_products = await cscart.get_popular_products(limit=10)

        # Deduplicate
        seen = set()
        all_products = []
        for p in new_products + popular_products:
            if p["cscart_id"] not in seen:
                seen.add(p["cscart_id"])
                all_products.append(p)

        await models.update_session(session_id, products_fetched=len(all_products))

        if not all_products:
            await _notify_admins("⚠️ Нет товаров для генерации.")
            await models.update_session(session_id, status="failed")
            return

        # Step 2: AI scoring
        scored = await claude_stylist.select_and_score_products(all_products)
        selected = [s for s in scored if s.get("selected", False)]

        if not selected:
            scored.sort(key=lambda x: x.get("score", 0), reverse=True)
            selected = scored[:PRODUCTS_TO_SELECT_DAILY]
            for s in selected:
                s["selected"] = True

        await models.update_session(session_id, products_selected=len(selected))

        # Save all scored products
        product_map = {p["cscart_id"]: p for p in all_products}
        for s in scored:
            cid = s["cscart_id"]
            if cid in product_map:
                p = product_map[cid]
                await models.upsert_product(
                    cscart_id=cid,
                    name=p["name"],
                    category=p.get("category"),
                    image_url=p.get("image_url"),
                    price=p.get("price"),
                    vendor=p.get("vendor"),
                    ai_score=s.get("score", 0),
                )

        # Step 3-4: Generate prompts and create tasks
        total_tasks = 0
        task_ids = []

        for sel in selected:
            cid = sel["cscart_id"]
            if cid not in product_map:
                continue

            product = product_map[cid]

            # Idempotency check
            if await models.product_has_video_today(cid):
                logger.info(f"Skipping {cid} — already generated today")
                continue

            db_product = await models.get_product_by_cscart_id(cid)
            if not db_product:
                continue

            prompts = await claude_stylist.generate_prompts(product)

            for prompt_data in prompts:
                prompt_text = prompt_data.get("prompt", "")
                prompt_type = prompt_data.get("type", "unknown")
                if not prompt_text:
                    continue

                try:
                    klingai_task_id = await klingai.create_video_task(
                        image_url=product["image_url"],
                        prompt=prompt_text,
                    )
                    task_id = await models.create_video_task(
                        product_id=db_product["id"],
                        klingai_task_id=klingai_task_id,
                        prompt=prompt_text,
                        prompt_type=prompt_type,
                    )
                    task_ids.append(task_id)
                    total_tasks += 1
                except Exception as e:
                    logger.error(f"Failed to create task for {cid}: {e}")

        await models.update_session(session_id, videos_generated=total_tasks)
        await _notify_admins(
            f"🎬 Отправлено {total_tasks} видео на генерацию.\n"
            f"Жду результатов..."
        )

        if not task_ids:
            await _notify_admins("⚠️ Не удалось создать ни одной задачи.")
            await models.update_session(session_id, status="failed")
            return

        # Step 5: Poll and notify
        completed = 0
        for task_id in task_ids:
            task = await models.get_video_task(task_id)
            if not task or not task["klingai_task_id"]:
                continue

            result = await klingai.poll_task_until_done(task["klingai_task_id"])
            status = result.get("status", "failed")

            if status == "succeed":
                video_url = result.get("video_url", "")
                await models.update_video_task(
                    task_id, status="succeed", video_url=video_url
                )
                # Send to admins for approval
                task_with_product = await models.get_task_with_product(task_id)
                if task_with_product and _bot:
                    for admin_id in TELEGRAM_ADMIN_IDS:
                        try:
                            from bot.handlers import _send_video_for_approval
                            await _send_video_for_approval(
                                _bot, admin_id, task_with_product
                            )
                        except Exception as e:
                            logger.error(f"Error sending video to admin: {e}")
                completed += 1
            else:
                error = result.get("error", "Unknown")
                await models.update_video_task(task_id, status="failed")
                logger.warning(f"Task {task_id} failed: {error}")

            await asyncio.sleep(2)

        await models.update_session(session_id, status="completed")
        await _notify_admins(
            f"✅ Ежедневная генерация завершена!\n"
            f"📊 {completed}/{total_tasks} видео готовы к одобрению.\n"
            f"Используйте /queue для просмотра."
        )

    except Exception as e:
        logger.error(f"Daily generation job error: {e}", exc_info=True)
        await models.update_session(session_id, status="failed")
        await _notify_admins(f"❌ Ошибка ежедневной генерации: {e}")
