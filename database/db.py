import aiosqlite
import logging

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_db_connection: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get the shared database connection, creating it if needed."""
    global _db_connection
    if _db_connection is None:
        _db_connection = await aiosqlite.connect(DATABASE_PATH)
        _db_connection.row_factory = aiosqlite.Row
        await _db_connection.execute("PRAGMA journal_mode=WAL")
        await _db_connection.execute("PRAGMA foreign_keys=ON")
    return _db_connection


async def init_database():
    """Create all tables if they don't exist."""
    db = await get_db()

    await db.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cscart_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            image_url TEXT,
            price REAL,
            vendor TEXT,
            ai_score REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS video_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            klingai_task_id TEXT,
            prompt TEXT,
            prompt_type TEXT,
            status TEXT DEFAULT 'submitted',
            video_url TEXT,
            telegram_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS generation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            products_fetched INTEGER DEFAULT 0,
            products_selected INTEGER DEFAULT 0,
            videos_generated INTEGER DEFAULT 0,
            videos_approved INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        )
    """)

    # Indexes for common queries
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_tasks_status 
        ON video_tasks(status)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_tasks_product 
        ON video_tasks(product_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_cscart_id 
        ON products(cscart_id)
    """)

    await db.commit()
    logger.info("Database initialized successfully")


async def close_database():
    """Close the database connection."""
    global _db_connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed")
