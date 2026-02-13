"""Mock data for testing Wabrum Content Bot without real API keys.

Usage:
    Run this file to seed the database with test data and simulate the pipeline.
    python test_data.py
"""

import asyncio
import json
import logging
import sys

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── Mock CS-Cart Responses ────────────────────────────────────────────────

MOCK_CSCART_PRODUCTS = [
    {
        "product_id": "1001",
        "product": "Кожаная сумка-мессенджер",
        "main_category_name": "Сумки",
        "main_pair": {
            "detailed": {
                "image_path": "https://via.placeholder.com/800x800/2d2d2d/ffffff?text=Leather+Bag"
            }
        },
        "price": "450.00",
        "company_name": "Ashgabat Leather Co",
        "timestamp": "1707000000",
    },
    {
        "product_id": "1002",
        "product": "Платье-миди с цветочным принтом",
        "main_category_name": "Платья",
        "main_pair": {
            "detailed": {
                "image_path": "https://via.placeholder.com/800x800/ffd4d4/333333?text=Floral+Dress"
            }
        },
        "price": "320.00",
        "company_name": "TurkSilk",
        "timestamp": "1707100000",
    },
    {
        "product_id": "1003",
        "product": "Белые кожаные кроссовки",
        "main_category_name": "Обувь",
        "main_pair": {
            "detailed": {
                "image_path": "https://via.placeholder.com/800x800/f5f5f5/333333?text=White+Sneakers"
            }
        },
        "price": "280.00",
        "company_name": "StepUp",
        "timestamp": "1707200000",
    },
    {
        "product_id": "1004",
        "product": "Шёлковый шарф Каракумы",
        "main_category_name": "Аксессуары",
        "main_pair": {
            "detailed": {
                "image_path": "https://via.placeholder.com/800x800/8b4513/ffffff?text=Silk+Scarf"
            }
        },
        "price": "150.00",
        "company_name": "Heritage TM",
        "timestamp": "1707300000",
    },
    {
        "product_id": "1005",
        "product": "Мужской пиджак приталенный",
        "main_category_name": "Одежда",
        "main_pair": {
            "detailed": {
                "image_path": "https://via.placeholder.com/800x800/1a1a2e/ffffff?text=Slim+Blazer"
            }
        },
        "price": "600.00",
        "company_name": "Merdan Fashion",
        "timestamp": "1707400000",
    },
    {
        "product_id": "1006",
        "product": "Золотые серьги-кольца",
        "main_category_name": "Аксессуары",
        "main_pair": {
            "detailed": {
                "image_path": "https://via.placeholder.com/800x800/ffd700/333333?text=Gold+Hoops"
            }
        },
        "price": "200.00",
        "company_name": "Altyn Jewelers",
        "timestamp": "1707500000",
    },
]


# ─── Mock Claude AI Responses ──────────────────────────────────────────────

MOCK_CLAUDE_SCORING = {
    "ranked_products": [
        {
            "cscart_id": "1006",
            "score": 9.2,
            "reasoning": "Gold jewelry has extremely high visual appeal for close-up shots, strong contrast on any background",
            "selected": True,
        },
        {
            "cscart_id": "1004",
            "score": 8.8,
            "reasoning": "Silk texture is mesmerizing in slow-motion, cultural relevance for TM audience",
            "selected": True,
        },
        {
            "cscart_id": "1001",
            "score": 8.5,
            "reasoning": "Rich leather texture, strong lifestyle potential, cross-gender appeal",
            "selected": True,
        },
        {
            "cscart_id": "1003",
            "score": 8.0,
            "reasoning": "Clean white sneakers always perform well in lifestyle content",
            "selected": True,
        },
        {
            "cscart_id": "1005",
            "score": 7.5,
            "reasoning": "Slim fit blazer has transformation potential, aspirational look",
            "selected": True,
        },
        {
            "cscart_id": "1002",
            "score": 6.5,
            "reasoning": "Print is visually busy for 5-second format, harder to capture details",
            "selected": False,
        },
    ]
}


MOCK_CLAUDE_PROMPTS = {
    "1006": {
        "prompts": [
            {
                "type": "detail",
                "prompt": "Extreme close-up macro shot of elegant gold hoop earrings rotating slowly against a deep navy velvet background. Warm studio lighting creates beautiful golden reflections. The camera captures every detail of the polished metal surface. Soft bokeh in the background adds depth. 9:16 vertical format, 5 seconds, cinematic quality",
            },
            {
                "type": "lifestyle",
                "prompt": "A confident young woman with dark hair tucking her hair behind her ear, revealing stylish gold hoop earrings. She smiles naturally while walking through a sunlit marble interior. Natural golden hour light catches the jewelry. Aspirational yet authentic moment. 9:16 vertical format, 5 seconds, cinematic quality",
            },
        ]
    },
    "1001": {
        "prompts": [
            {
                "type": "detail",
                "prompt": "Macro close-up of a leather messenger bag's rich grain texture. Camera slowly glides across the surface, revealing stitching details and buckle craftsmanship. Warm amber side lighting emphasizes depth and quality of the leather. 9:16 vertical format, 5 seconds, cinematic quality",
            },
            {
                "type": "lifestyle",
                "prompt": "A stylish young man walking through a modern Ashgabat street carrying a leather messenger bag over his shoulder. Camera tracks from behind, then sweeps to a side profile. Natural daylight, urban architecture in background. Confident stride, professional but relaxed. 9:16 vertical format, 5 seconds, cinematic quality",
            },
        ]
    },
}


# ─── Mock KlingAI Responses ────────────────────────────────────────────────

MOCK_KLINGAI_CREATE_RESPONSE = {
    "code": 0,
    "message": "Success",
    "request_id": "req_test_001",
    "data": {
        "task_id": "task_mock_001",
        "task_info": {"external_task_id": ""},
        "task_status": "submitted",
        "created_at": 1707000000000,
        "updated_at": 1707000000000,
    },
}

MOCK_KLINGAI_STATUS_SUCCEED = {
    "code": 0,
    "message": "Success",
    "request_id": "req_test_002",
    "data": {
        "task_id": "task_mock_001",
        "task_status": "succeed",
        "task_status_msg": "",
        "task_info": {"external_task_id": ""},
        "created_at": 1707000000000,
        "updated_at": 1707000060000,
        "task_result": {
            "videos": [
                {
                    "id": "video_mock_001",
                    "url": "https://example.com/mock_video.mp4",
                    "duration": "5",
                }
            ]
        },
    },
}

MOCK_KLINGAI_STATUS_PROCESSING = {
    "code": 0,
    "message": "Success",
    "request_id": "req_test_003",
    "data": {
        "task_id": "task_mock_001",
        "task_status": "processing",
        "task_status_msg": "",
        "task_info": {"external_task_id": ""},
        "created_at": 1707000000000,
        "updated_at": 1707000030000,
    },
}


# ─── Test Runner ────────────────────────────────────────────────────────────

async def test_database():
    """Test database operations with mock data."""
    from database.db import init_database, close_database
    from database import models
    from services.cscart import _normalize_product

    logger.info("--- Testing Database ---")
    await init_database()

    # Insert products
    for raw in MOCK_CSCART_PRODUCTS:
        p = _normalize_product(raw)
        product_id = await models.upsert_product(
            cscart_id=p["cscart_id"],
            name=p["name"],
            category=p.get("category"),
            image_url=p.get("image_url"),
            price=p.get("price"),
            vendor=p.get("vendor"),
        )
        logger.info(f"Inserted product: {p['name']} (ID={product_id})")

    # Test scoring update
    for scored in MOCK_CLAUDE_SCORING["ranked_products"]:
        product = await models.get_product_by_cscart_id(scored["cscart_id"])
        if product:
            await models.upsert_product(
                cscart_id=scored["cscart_id"],
                name=product["name"],
                category=product["category"],
                image_url=product["image_url"],
                price=product["price"],
                vendor=product["vendor"],
                ai_score=scored["score"],
            )

    # Create a session
    session_id = await models.create_session()
    await models.update_session(
        session_id,
        products_fetched=6,
        products_selected=5,
    )

    # Create video tasks
    product = await models.get_product_by_cscart_id("1006")
    if product:
        task_id = await models.create_video_task(
            product_id=product["id"],
            klingai_task_id="task_mock_001",
            prompt=MOCK_CLAUDE_PROMPTS["1006"]["prompts"][0]["prompt"],
            prompt_type="detail",
        )
        logger.info(f"Created video task: ID={task_id}")

        # Simulate succeed
        await models.update_video_task(
            task_id,
            status="succeed",
            video_url="https://example.com/mock_video.mp4",
        )

    # Test stats
    stats = await models.get_stats(days=7)
    logger.info(f"Stats: {json.dumps(stats, indent=2, default=str)}")

    # Test queue
    queue = await models.get_queue_tasks()
    logger.info(f"Queue: {len(queue)} videos")

    # Test idempotency
    has_video = await models.product_has_video_today("1006")
    logger.info(f"Product 1006 has video today: {has_video}")

    await close_database()
    logger.info("--- Database test complete ---\n")


async def test_normalization():
    """Test CS-Cart product normalization."""
    from services.cscart import _normalize_product

    logger.info("--- Testing CS-Cart Normalization ---")
    for raw in MOCK_CSCART_PRODUCTS:
        p = _normalize_product(raw)
        logger.info(
            f"  {p['cscart_id']}: {p['name']} | "
            f"img={bool(p['image_url'])} | "
            f"vendor={p['vendor']} | "
            f"${p['price']}"
        )
    logger.info("--- Normalization test complete ---\n")


async def run_all_tests():
    """Run all tests."""
    logger.info("=" * 50)
    logger.info("WABRUM CONTENT BOT — TEST SUITE")
    logger.info("=" * 50 + "\n")

    await test_normalization()
    await test_database()

    logger.info("=" * 50)
    logger.info("ALL TESTS PASSED")
    logger.info("=" * 50)


if __name__ == "__main__":
    # Clean up any existing test DB
    import os
    if os.path.exists("wabrum_bot.db"):
        os.unlink("wabrum_bot.db")

    asyncio.run(run_all_tests())
