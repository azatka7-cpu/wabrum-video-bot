import logging
from datetime import datetime, timedelta, timezone

from database.db import get_db

logger = logging.getLogger(__name__)


# ─── Products ───────────────────────────────────────────────────────────────

async def upsert_product(
    cscart_id: str,
    name: str,
    category: str | None = None,
    image_url: str | None = None,
    price: float | None = None,
    vendor: str | None = None,
    ai_score: float = 0,
) -> int:
    """Insert or update a product. Returns the internal product ID."""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO products (cscart_id, name, category, image_url, price, vendor, ai_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cscart_id) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            image_url = excluded.image_url,
            price = excluded.price,
            vendor = excluded.vendor,
            ai_score = excluded.ai_score
        """,
        (cscart_id, name, category, image_url, price, vendor, ai_score),
    )
    await db.commit()
    # Get the id (either new or existing)
    row = await db.execute_fetchall(
        "SELECT id FROM products WHERE cscart_id = ?", (cscart_id,)
    )
    return row[0][0]


async def get_product(product_id: int) -> dict | None:
    """Get a product by internal ID."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_product_by_cscart_id(cscart_id: str) -> dict | None:
    """Get a product by CS-Cart ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM products WHERE cscart_id = ?", (cscart_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def product_has_video_today(cscart_id: str) -> bool:
    """Check if a product already has a video generated today."""
    db = await get_db()
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    cursor = await db.execute(
        """
        SELECT COUNT(*) FROM video_tasks vt
        JOIN products p ON p.id = vt.product_id
        WHERE p.cscart_id = ? AND vt.created_at >= ?
        """,
        (cscart_id, today_start.isoformat()),
    )
    row = await cursor.fetchone()
    return row[0] > 0


# ─── Video Tasks ────────────────────────────────────────────────────────────

async def create_video_task(
    product_id: int,
    klingai_task_id: str,
    prompt: str,
    prompt_type: str,
) -> int:
    """Create a video task record. Returns the task ID."""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO video_tasks (product_id, klingai_task_id, prompt, prompt_type, status)
        VALUES (?, ?, ?, ?, 'submitted')
        """,
        (product_id, klingai_task_id, prompt, prompt_type),
    )
    await db.commit()
    return cursor.lastrowid


async def update_video_task(task_id: int, **kwargs) -> None:
    """Update video task fields dynamically."""
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [task_id]
    db = await get_db()
    await db.execute(
        f"UPDATE video_tasks SET {set_clause} WHERE id = ?", values
    )
    await db.commit()


async def get_video_task(task_id: int) -> dict | None:
    """Get a video task by internal ID."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM video_tasks WHERE id = ?", (task_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_pending_tasks() -> list[dict]:
    """Get all tasks with status submitted or processing."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM video_tasks WHERE status IN ('submitted', 'processing')"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_tasks_by_status(status: str) -> list[dict]:
    """Get all tasks with a given status."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM video_tasks WHERE status = ?", (status,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_queue_tasks() -> list[dict]:
    """Get tasks that are ready for approval (succeed, not yet approved/rejected)."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT vt.*, p.name as product_name, p.vendor, p.price, p.image_url, p.ai_score
        FROM video_tasks vt
        JOIN products p ON p.id = vt.product_id
        WHERE vt.status = 'succeed'
        ORDER BY vt.created_at DESC
        """
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_task_with_product(task_id: int) -> dict | None:
    """Get a task with its product info joined."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT vt.*, p.name as product_name, p.vendor, p.price, p.image_url,
               p.ai_score, p.cscart_id
        FROM video_tasks vt
        JOIN products p ON p.id = vt.product_id
        WHERE vt.id = ?
        """,
        (task_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


# ─── Generation Sessions ───────────────────────────────────────────────────

async def create_session() -> int:
    """Create a new generation session. Returns session ID."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO generation_sessions (status) VALUES ('running')"
    )
    await db.commit()
    return cursor.lastrowid


async def update_session(session_id: int, **kwargs) -> None:
    """Update session fields dynamically."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [session_id]
    db = await get_db()
    await db.execute(
        f"UPDATE generation_sessions SET {set_clause} WHERE id = ?", values
    )
    await db.commit()


# ─── Statistics ─────────────────────────────────────────────────────────────

async def get_stats(days: int = 7) -> dict:
    """Get generation statistics for the last N days."""
    db = await get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    stats = {}

    for status in ("submitted", "processing", "succeed", "approved", "rejected", "published", "failed"):
        cursor = await db.execute(
            "SELECT COUNT(*) FROM video_tasks WHERE status = ? AND created_at >= ?",
            (status, since),
        )
        row = await cursor.fetchone()
        stats[status] = row[0]

    # Total generated
    cursor = await db.execute(
        "SELECT COUNT(*) FROM video_tasks WHERE created_at >= ?", (since,)
    )
    row = await cursor.fetchone()
    stats["total"] = row[0]

    # Top prompt types by approval
    cursor = await db.execute(
        """
        SELECT prompt_type, COUNT(*) as cnt
        FROM video_tasks
        WHERE status = 'approved' AND created_at >= ?
        GROUP BY prompt_type
        ORDER BY cnt DESC
        LIMIT 3
        """,
        (since,),
    )
    rows = await cursor.fetchall()
    stats["top_prompt_types"] = [(r[0], r[1]) for r in rows]

    # Last session
    cursor = await db.execute(
        "SELECT * FROM generation_sessions ORDER BY id DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    stats["last_session"] = dict(row) if row else None

    return stats
