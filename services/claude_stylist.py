"""AI stylist powered by Anthropic Claude API.

Handles product scoring/selection and KlingAI prompt generation.
"""

import json
import logging

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, PRODUCTS_TO_SELECT_DAILY

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SCORING_SYSTEM_PROMPT = """You are a visual content strategist for Wabrum.com, a fashion marketplace in Turkmenistan.
Your job is to analyze fashion products and select those with the highest potential for 
short-form video advertising (TikTok, Instagram Reels).

Scoring criteria (1-10):
- Visual appeal: rich texture, interesting details, strong color contrast
- Category weight: accessories and shoes score higher (easier to film), complex dresses lower
- Newness: recently added products score higher
- Lifestyle potential: can this product tell a story in 5 seconds?

Target audience: Central Asian women and men, ages 18-35, aspirational but accessible.

Always respond in valid JSON only. No explanations outside JSON."""


PROMPT_GENERATION_SYSTEM = """You are a KlingAI video prompt specialist for Wabrum.com fashion marketplace.
Generate short-form video prompts for KlingAI 3.0, which produces hyper-realistic
lifestyle videos with natural human movement.

IMPORTANT RULES:
- All prompts must be in English
- Always end with: "9:16 vertical format, 5 seconds, cinematic quality"
- Prompts must be 50-120 words
- Avoid: excessive text overlays, unrealistic physics, logo placement
- Prioritize: natural lighting, authentic human interaction with product, aspirational but relatable scenes
- KlingAI 3.0 excels at realistic human motion — use this for lifestyle shots

5 prompt types to choose from (pick 2 most suitable for the product):
1. detail — macro close-up of texture, stitching, materials
2. lifestyle — person wearing/using the product in a realistic scene
3. flatlay — product laid on a surface with smooth camera movement
4. transformation — dramatic reveal of product from darkness/fog
5. silhouette — person silhouette wearing the product against atmospheric backdrop

Always respond in valid JSON only."""


async def select_and_score_products(products: list[dict]) -> list[dict]:
    """Send products to Claude for scoring and selection.

    Args:
        products: List of product dicts with keys: cscart_id, name, category,
                  image_url, price, vendor

    Returns:
        List of dicts: {cscart_id, score, reasoning, selected}
        Sorted by score descending, top N marked as selected.
    """
    client = _get_client()

    # Prepare a compact product list for Claude
    product_summaries = []
    for p in products:
        product_summaries.append({
            "cscart_id": p["cscart_id"],
            "name": p["name"],
            "category": p.get("category", ""),
            "price": p.get("price", 0),
            "vendor": p.get("vendor", ""),
        })

    user_message = json.dumps({
        "products": product_summaries,
        "select_top": PRODUCTS_TO_SELECT_DAILY,
    }, ensure_ascii=False)

    try:
        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=SCORING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract JSON from response
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        ranked = result.get("ranked_products", [])

        logger.info(
            f"Claude scored {len(ranked)} products, "
            f"top score: {ranked[0]['score'] if ranked else 'N/A'}"
        )
        return ranked

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude scoring response: {e}")
        # Fallback: return all products with default score
        return [
            {"cscart_id": p["cscart_id"], "score": 5.0, "reasoning": "Fallback", "selected": i < PRODUCTS_TO_SELECT_DAILY}
            for i, p in enumerate(products)
        ]
    except anthropic.APIError as e:
        logger.error(f"Claude API error during scoring: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in product scoring: {e}")
        raise


async def generate_prompts(product: dict) -> list[dict]:
    """Generate 2 KlingAI video prompts for a product.

    Args:
        product: Dict with keys: cscart_id, name, category, image_url, price, vendor

    Returns:
        List of dicts: [{type: str, prompt: str}, ...]
    """
    client = _get_client()

    user_message = json.dumps({
        "product": {
            "name": product["name"],
            "category": product.get("category", ""),
            "price": product.get("price", 0),
            "vendor": product.get("vendor", ""),
            "image_url": product.get("image_url", ""),
        },
        "num_prompts": 2,
    }, ensure_ascii=False)

    try:
        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=PROMPT_GENERATION_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        prompts = result.get("prompts", [])

        logger.info(
            f"Generated {len(prompts)} prompts for '{product['name']}': "
            f"types={[p['type'] for p in prompts]}"
        )
        return prompts

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude prompt response: {e}")
        # Fallback prompts
        return [
            {
                "type": "detail",
                "prompt": (
                    f"Extreme close-up macro shot of a {product['name']}, "
                    f"showcasing the rich texture and fine craftsmanship. "
                    f"Smooth camera movement reveals intricate details. "
                    f"Soft natural lighting on a clean background. "
                    f"9:16 vertical format, 5 seconds, cinematic quality"
                ),
            },
            {
                "type": "lifestyle",
                "prompt": (
                    f"A stylish young person confidently walking through a modern city street, "
                    f"wearing a {product['name']}. Natural sunlight creates soft shadows. "
                    f"The camera follows with a smooth tracking shot, capturing the natural "
                    f"movement of fabric and confident stride. Aspirational and authentic. "
                    f"9:16 vertical format, 5 seconds, cinematic quality"
                ),
            },
        ]
    except anthropic.APIError as e:
        logger.error(f"Claude API error during prompt generation: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in prompt generation: {e}")
        raise
