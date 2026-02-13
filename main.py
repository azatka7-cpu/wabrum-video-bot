"""Wabrum Content Bot — entry point.

A Telegram bot for automated AI-powered video content generation
for Wabrum.com fashion marketplace.
"""

import asyncio
import logging
import signal
import sys

from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN
from database.db import init_database, close_database
from bot.handlers import register_handlers
from services.scheduler import init_scheduler, start_scheduler, stop_scheduler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Reduce noise from httpx/httpcore
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def post_init(application: Application):
    """Called after the Application is initialized."""
    logger.info("Bot initialized, starting scheduler...")
    init_scheduler(application.bot)
    start_scheduler()


async def post_shutdown(application: Application):
    """Called during Application shutdown."""
    logger.info("Shutting down...")
    stop_scheduler()
    await close_database()
    logger.info("Shutdown complete")


def main():
    """Start the Wabrum Content Bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")
        sys.exit(1)

    logger.info("Starting Wabrum Content Bot...")

    # Initialize database synchronously before starting the event loop
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init_database())
    loop.close()

    # Build the Telegram application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    register_handlers(application)

    # Run the bot with polling
    logger.info("Bot is starting polling...")
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
