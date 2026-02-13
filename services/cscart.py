"""CS-Cart API client for fetching products from Wabrum.com."""

import base64
import logging
import time
from urllib.parse import urljoin

import aiohttp

from config import CSCART_API_URL, CSCART_API_EMAIL, CSCART_API_KEY

logger = logging.getLogger(__name__)


def _auth_header() -> str:
    """Build Basic Auth header value."""
    credentials = f"{CSCART_API_EMAIL}:{CSCART_API_KEY}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _headers() -> dict:
    return {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base_url() -> str:
    """Get the site base URL from the API URL (e.g. https://wabrum.com from https://wabrum.com/api)."""
    if CSCART_API_URL.endswith("/api"):
        return CSCART_API_URL[: -len("/api")]
    return CSCART_API_URL.rsplit("/api", 1)[0]


def get_product_image_url(product_data: dict) -> str | None:
    """Extract the image URL from CS-Cart product data.

    CS-Cart returns image paths in main_pair.detailed.image_path or
    main_pair.icon.image_path. Paths may be relative, so we prepend
    the base URL when needed.
    """
    main_pair = product_data.get("main_pair")
    if not main_pair:
        return None

    image_path = None
    detailed = main_pair.get("detailed")
    if detailed:
        image_path = detailed.get("image_path") or detailed.get("http_image_path")

    if not image_path:
        icon = main_pair.get("icon")
        if icon:
            image_path = icon.get("image_path") or icon.get("http_image_path")

    if not image_path:
        return None

    # If it's already absolute, return as-is
    if image_path.startswith("http"):
        return image_path

    # Otherwise, prepend base URL
    return urljoin(_base_url() + "/", image_path.lstrip("/"))


def _normalize_product(raw: dict) -> dict:
    """Transform raw CS-Cart product data into our internal format."""
    return {
        "cscart_id": str(raw.get("product_id", "")),
        "name": raw.get("product", "Unknown"),
        "category": raw.get("main_category_name", raw.get("main_category", "")),
        "image_url": get_product_image_url(raw),
        "price": float(raw.get("price", 0)),
        "vendor": raw.get("company_name", ""),
        "timestamp": raw.get("timestamp", 0),
    }


async def get_products(
    limit: int = 20,
    sort_by: str = "timestamp",
    sort_order: str = "desc",
) -> list[dict]:
    """Fetch active products from CS-Cart.

    Parameters:
        limit: Maximum number of products to return.
        sort_by: Field to sort by (timestamp, popularity, etc.)
        sort_order: asc or desc
    """
    url = f"{CSCART_API_URL}/products"
    params = {
        "items_per_page": limit,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "status": "A",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_headers(), params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()

        # CS-Cart wraps products in a "products" key
        products_raw = data.get("products", data) if isinstance(data, dict) else data
        if isinstance(products_raw, dict):
            # Sometimes CS-Cart returns {product_id: {...}, ...}
            products_raw = list(products_raw.values())

        products = [_normalize_product(p) for p in products_raw if isinstance(p, dict)]
        # Filter out products without images
        products = [p for p in products if p["image_url"]]
        logger.info(f"Fetched {len(products)} products from CS-Cart (sort={sort_by})")
        return products

    except aiohttp.ClientError as e:
        logger.error(f"CS-Cart API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching products: {e}")
        raise


async def get_new_products(days: int = 7, limit: int = 20) -> list[dict]:
    """Fetch products added in the last N days."""
    products = await get_products(limit=limit, sort_by="timestamp", sort_order="desc")
    cutoff = int(time.time()) - (days * 86400)
    return [p for p in products if int(p.get("timestamp", 0)) >= cutoff]


async def get_popular_products(limit: int = 20) -> list[dict]:
    """Fetch products sorted by popularity."""
    return await get_products(limit=limit, sort_by="popularity", sort_order="desc")
