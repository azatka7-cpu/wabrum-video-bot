"""Telegram bot handlers for Wabrum Content Bot."""

import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from config import TELEGRAM_ADMIN_IDS
from database import models
from services import cscart, claude_stylist, klingai
from bot.keyboards import video_approval_keyboard, approved_video_keyboard

logger = logging.getLogger(__name__)


# ─── Decorators ─────────────────────────────────────────────────────────────

def admin_only(func):
    """Decorator that restricts handler to admin users only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in TELEGRAM_ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещён")
            return
        return await func(update, context)
    return wrapper


# ─── Command Handlers ───────────────────────────────────────────────────────

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — greeting + system status."""
    stats = await models.get_stats(days=7)
    session = stats.get("last_session")

    text = (
        "👋 Привет! Я Wabrum Content Bot.\n\n"
        "Я автоматически создаю видеоконтент для товаров Wabrum.com "
        "с помощью AI-стилиста и KlingAI 3.0.\n\n"
        "📊 Статус за 7 дней:\n"
        f"  • Видео в очереди: {stats.get('succeed', 0)}\n"
        f"  • Одобрено: {stats.get('approved', 0)}\n"
        f"  • Опубликовано: {stats.get('published', 0)}\n"
        f"  • Всего сгенерировано: {stats.get('total', 0)}\n"
    )

    if session:
        text += f"\n🕐 Последняя генерация: {session.get('started_at', 'N/A')}\n"

    text += (
        "\n📋 Команды:\n"
        "/generate — запустить генерацию\n"
        "/queue — очередь на одобрение\n"
        "/stats — статистика\n"
        "/help — справка"
    )
    await update.message.reply_text(text)


@admin_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    text = (
        "📋 Доступные команды:\n\n"
        "/start — статус системы\n"
        "/generate — запустить генерацию видео прямо сейчас\n"
        "/queue — показать видео для одобрения\n"
        "/stats — статистика за 7 дней\n"
        "/help — эта справка\n\n"
        "💡 Бот автоматически запускает генерацию каждый день в 09:00 (Ашхабад)."
    )
    await update.message.reply_text(text)


@admin_only
async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate — run manual generation pipeline."""
    chat_id = update.effective_chat.id
    msg = await update.message.reply_text("🔄 Шаг 1/4: Получаю товары из Wabrum.com...")

    try:
        # Step 1: Fetch products
        new_products = await cscart.get_new_products(days=7, limit=15)
        popular_products = await cscart.get_popular_products(limit=10)

        # Deduplicate by cscart_id
        seen = set()
        all_products = []
        for p in new_products + popular_products:
            if p["cscart_id"] not in seen:
                seen.add(p["cscart_id"])
                all_products.append(p)

        if not all_products:
            await msg.edit_text("⚠️ Не удалось получить товары из CS-Cart.")
            return

        await msg.edit_text(
            f"✅ Получено {len(all_products)} товаров\n\n"
            f"🔄 Шаг 2/4: AI-стилист анализирует товары..."
        )

        # Step 2: AI scoring and selection
        scored = await claude_stylist.select_and_score_products(all_products)
        selected = [s for s in scored if s.get("selected", False)]

        if not selected:
            # Fallback: take top 5 by score
            scored.sort(key=lambda x: x.get("score", 0), reverse=True)
            selected = scored[:5]
            for s in selected:
                s["selected"] = True

        # Save products to DB
        session_id = await models.create_session()
        await models.update_session(session_id, products_fetched=len(all_products), products_selected=len(selected))

        # Map cscart_id to product data
        product_map = {p["cscart_id"]: p for p in all_products}

        # Update scores in DB
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

        await msg.edit_text(
            f"✅ Получено {len(all_products)} товаров\n"
            f"✅ Выбрано {len(selected)} товаров для генерации\n\n"
            f"🔄 Шаг 3/4: Генерирую промпты и отправляю в KlingAI 3.0..."
        )

        # Step 3: Generate prompts and create video tasks
        total_tasks = 0
        tasks_created = []

        for sel in selected:
            cid = sel["cscart_id"]
            if cid not in product_map:
                continue

            product = product_map[cid]

            # Check idempotency
            if await models.product_has_video_today(cid):
                logger.info(f"Skipping product {cid} — already has video today")
                continue

            # Get DB product ID
            db_product = await models.get_product_by_cscart_id(cid)
            if not db_product:
                continue
            product_id = db_product["id"]

            # Generate prompts from Claude
            prompts = await claude_stylist.generate_prompts(product)

            for prompt_data in prompts:
                prompt_text = prompt_data.get("prompt", "")
                prompt_type = prompt_data.get("type", "unknown")

                if not prompt_text:
                    continue

                try:
                    # Create KlingAI task
                    klingai_task_id = await klingai.create_video_task(
                        image_url=product["image_url"],
                        prompt=prompt_text,
                    )

                    # Save to DB
                    task_id = await models.create_video_task(
                        product_id=product_id,
                        klingai_task_id=klingai_task_id,
                        prompt=prompt_text,
                        prompt_type=prompt_type,
                    )
                    tasks_created.append(task_id)
                    total_tasks += 1
                except Exception as e:
                    logger.error(f"Failed to create video task for {cid}: {e}")

        await models.update_session(session_id, videos_generated=total_tasks)

        await msg.edit_text(
            f"✅ Получено {len(all_products)} товаров\n"
            f"✅ Выбрано {len(selected)} товаров для генерации\n"
            f"✅ {total_tasks} видео в очереди генерации\n\n"
            f"🔄 Шаг 4/4: Жду результатов (обычно 10-15 минут)...\n"
            f"Я пришлю каждое видео отдельным сообщением, когда оно будет готово."
        )

        # Step 4: Start background polling
        if tasks_created:
            asyncio.create_task(
                _poll_and_send_videos(context.bot, chat_id, tasks_created, session_id)
            )
        else:
            await msg.edit_text(
                f"✅ Получено {len(all_products)} товаров\n"
                f"✅ Выбрано {len(selected)} товаров для генерации\n"
                f"⚠️ Не удалось создать ни одной задачи генерации."
            )
            await models.update_session(session_id, status="failed")

    except Exception as e:
        logger.error(f"Generation pipeline error: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка при генерации: {e}")


@admin_only
async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /queue — show videos awaiting approval."""
    tasks = await models.get_queue_tasks()

    if not tasks:
        await update.message.reply_text("📭 Очередь пуста — нет видео для одобрения.")
        return

    await update.message.reply_text(f"📋 В очереди {len(tasks)} видео. Отправляю...")

    for task in tasks[:10]:  # Limit to 10 at a time
        await _send_video_for_approval(context.bot, update.effective_chat.id, task)
        await asyncio.sleep(1)  # Avoid flood limits

    if len(tasks) > 10:
        await update.message.reply_text(
            f"... и ещё {len(tasks) - 10} видео. Используйте /queue снова."
        )


@admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats — show 7-day statistics."""
    stats = await models.get_stats(days=7)

    top_types = ""
    for ptype, count in stats.get("top_prompt_types", []):
        top_types += f"  • {ptype}: {count} одобрений\n"
    if not top_types:
        top_types = "  Нет данных\n"

    text = (
        "📊 Статистика за 7 дней:\n\n"
        f"🎬 Всего видео: {stats.get('total', 0)}\n"
        f"  • ⏳ В обработке: {stats.get('submitted', 0) + stats.get('processing', 0)}\n"
        f"  • ✅ Готовы к одобрению: {stats.get('succeed', 0)}\n"
        f"  • 👍 Одобрено: {stats.get('approved', 0)}\n"
        f"  • 👎 Отклонено: {stats.get('rejected', 0)}\n"
        f"  • 📤 Опубликовано: {stats.get('published', 0)}\n"
        f"  • ❌ Ошибки: {stats.get('failed', 0)}\n\n"
        f"🏆 Топ типы промптов:\n{top_types}"
    )
    await update.message.reply_text(text)


# ─── Callback Handlers ──────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all callback queries to the appropriate handler."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in TELEGRAM_ADMIN_IDS:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return

    data = query.data
    if data.startswith("approve_"):
        await _handle_approve(query, context)
    elif data.startswith("reject_"):
        await _handle_reject(query, context)
    elif data.startswith("regenerate_"):
        await _handle_regenerate(query, context)
    elif data.startswith("details_"):
        await _handle_details(query, context)
    elif data.startswith("publish_"):
        await _handle_publish(query, context)
    else:
        logger.warning(f"Unknown callback data: {data}")


async def _handle_approve(query, context):
    task_id = int(query.data.split("_", 1)[1])
    await models.update_video_task(task_id, status="approved")

    # Edit message to show approval
    old_text = query.message.caption or query.message.text or ""
    new_text = "✅ ОДОБРЕНО\n\n" + old_text
    try:
        await query.edit_message_caption(
            caption=new_text[:1024],
            reply_markup=approved_video_keyboard(task_id),
        )
    except Exception:
        await query.edit_message_reply_markup(
            reply_markup=approved_video_keyboard(task_id)
        )


async def _handle_reject(query, context):
    task_id = int(query.data.split("_", 1)[1])
    await models.update_video_task(task_id, status="rejected")

    old_text = query.message.caption or query.message.text or ""
    new_text = "❌ ОТКЛОНЕНО\n\n" + old_text
    try:
        await query.edit_message_caption(caption=new_text[:1024], reply_markup=None)
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)


async def _handle_regenerate(query, context):
    task_id = int(query.data.split("_", 1)[1])
    task = await models.get_task_with_product(task_id)
    if not task:
        await query.answer("❌ Задача не найдена", show_alert=True)
        return

    # Mark old task as rejected
    await models.update_video_task(task_id, status="rejected")
    old_text = query.message.caption or query.message.text or ""
    try:
        await query.edit_message_caption(
            caption="🔄 Перегенерация...\n\n" + old_text[:900],
            reply_markup=None,
        )
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)

    # Create new task with same product and prompt type
    chat_id = query.message.chat_id
    await context.bot.send_message(
        chat_id,
        f"🔄 Перегенерация видео для «{task['product_name']}»...\nТип: {task['prompt_type']}"
    )

    try:
        # Generate a new prompt of the same type
        product = {
            "name": task["product_name"],
            "category": "",
            "image_url": task["image_url"],
            "price": task["price"],
            "vendor": task["vendor"],
        }
        prompts = await claude_stylist.generate_prompts(product)

        # Find a prompt of the same type, or use the first one
        prompt_data = next(
            (p for p in prompts if p.get("type") == task["prompt_type"]),
            prompts[0] if prompts else None,
        )

        if not prompt_data:
            await context.bot.send_message(chat_id, "❌ Не удалось сгенерировать промпт")
            return

        klingai_task_id = await klingai.create_video_task(
            image_url=task["image_url"],
            prompt=prompt_data["prompt"],
        )

        new_task_id = await models.create_video_task(
            product_id=task["product_id"],
            klingai_task_id=klingai_task_id,
            prompt=prompt_data["prompt"],
            prompt_type=prompt_data["type"],
        )

        # Poll in background
        asyncio.create_task(
            _poll_and_send_videos(context.bot, chat_id, [new_task_id], None)
        )

    except Exception as e:
        logger.error(f"Regeneration error: {e}", exc_info=True)
        await context.bot.send_message(chat_id, f"❌ Ошибка перегенерации: {e}")


async def _handle_details(query, context):
    task_id = int(query.data.split("_", 1)[1])
    task = await models.get_task_with_product(task_id)
    if not task:
        await query.answer("❌ Задача не найдена", show_alert=True)
        return

    text = (
        f"ℹ️ Подробности задачи #{task_id}\n\n"
        f"👗 Товар: {task['product_name']}\n"
        f"🆔 CS-Cart ID: {task.get('cscart_id', 'N/A')}\n"
        f"🏪 Вендор: {task['vendor']}\n"
        f"💰 Цена: {task['price']} TMT\n"
        f"📊 AI-оценка: {task['ai_score']}/10\n"
        f"🎯 Тип промпта: {task['prompt_type']}\n"
        f"📝 Статус: {task['status']}\n"
        f"🕐 Создано: {task['created_at']}\n\n"
        f"📝 Промпт:\n{task['prompt']}"
    )
    await query.answer()
    await context.bot.send_message(query.message.chat_id, text[:4096])


async def _handle_publish(query, context):
    task_id = int(query.data.split("_", 1)[1])
    await models.update_video_task(task_id, status="published")

    old_text = query.message.caption or query.message.text or ""
    new_text = "📤 ОПУБЛИКОВАНО\n\n" + old_text
    try:
        await query.edit_message_caption(caption=new_text[:1024], reply_markup=None)
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)

    await context.bot.send_message(
        query.message.chat_id,
        "📤 Добавлено в очередь публикации"
    )


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _send_video_for_approval(bot, chat_id: int, task: dict):
    """Send a generated video to Telegram with approval buttons."""
    video_url = task.get("video_url")
    task_id = task["id"]

    caption = (
        f"🎬 Новое видео готово!\n\n"
        f"👗 {task.get('product_name', 'Товар')}\n"
        f"🏪 Вендор: {task.get('vendor', 'N/A')}\n"
        f"💰 Цена: {task.get('price', 0)} TMT\n"
        f"📊 AI-оценка: {task.get('ai_score', 0)}/10\n"
        f"🎯 Тип: {task.get('prompt_type', 'N/A')}\n\n"
        f"📝 Промпт:\n{task.get('prompt', '')[:300]}"
    )

    keyboard = video_approval_keyboard(task_id)

    if video_url:
        tmp_path = None
        try:
            # Download video to temp file
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
            os.close(tmp_fd)

            await klingai.download_video(video_url, tmp_path)

            file_size = os.path.getsize(tmp_path)

            with open(tmp_path, "rb") as video_file:
                if file_size > 50 * 1024 * 1024:
                    # Too large for video, send as document
                    sent = await bot.send_document(
                        chat_id=chat_id,
                        document=video_file,
                        caption=caption[:1024],
                        reply_markup=keyboard,
                    )
                else:
                    sent = await bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=caption[:1024],
                        reply_markup=keyboard,
                        supports_streaming=True,
                    )

            # Save telegram message ID
            await models.update_video_task(
                task_id, telegram_message_id=sent.message_id
            )

        except Exception as e:
            logger.error(f"Error sending video for task {task_id}: {e}")
            await bot.send_message(
                chat_id,
                f"❌ Не удалось отправить видео (задача #{task_id}): {e}\n"
                f"URL: {video_url}",
                reply_markup=keyboard,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    else:
        await bot.send_message(
            chat_id,
            f"⚠️ Видео не имеет URL (задача #{task_id})\n\n" + caption,
            reply_markup=keyboard,
        )


async def _poll_and_send_videos(
    bot, chat_id: int, task_ids: list[int], session_id: int | None
):
    """Background task: poll KlingAI for pending tasks and send results."""
    completed = 0
    total = len(task_ids)

    for task_id in task_ids:
        task = await models.get_video_task(task_id)
        if not task:
            continue

        klingai_task_id = task["klingai_task_id"]
        if not klingai_task_id:
            continue

        result = await klingai.poll_task_until_done(klingai_task_id)
        status = result.get("status", "failed")

        if status == "succeed":
            video_url = result.get("video_url", "")
            await models.update_video_task(
                task_id, status="succeed", video_url=video_url
            )
            # Send video for approval
            task_with_product = await models.get_task_with_product(task_id)
            if task_with_product:
                await _send_video_for_approval(bot, chat_id, task_with_product)
            completed += 1
        else:
            error = result.get("error", "Unknown error")
            await models.update_video_task(task_id, status="failed")
            await bot.send_message(
                chat_id,
                f"❌ Задача #{task_id} не удалась: {error}"
            )

        await asyncio.sleep(2)  # Small delay between sends

    # Update session
    if session_id:
        await models.update_session(
            session_id,
            videos_generated=total,
            status="completed",
        )

    if completed > 0:
        await bot.send_message(
            chat_id,
            f"✅ Генерация завершена: {completed}/{total} видео готовы к одобрению."
        )
    elif total > 0:
        await bot.send_message(
            chat_id,
            f"⚠️ Генерация завершена: ни одно видео не удалось ({total} задач)."
        )


def register_handlers(application):
    """Register all handlers with the Telegram application."""
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("generate", cmd_generate))
    application.add_handler(CommandHandler("queue", cmd_queue))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CallbackQueryHandler(callback_handler))
