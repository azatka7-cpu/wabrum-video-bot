"""KlingAI 3.0 API client using the Omni-Video O1 endpoint.

Handles video generation task creation, status polling, and result retrieval.
"""

import asyncio
import logging

import aiohttp

from config import (
    KLINGAI_API_URL,
    KLINGAI_API_KEY,
    KLINGAI_MODE,
    KLINGAI_ASPECT_RATIO,
    KLINGAI_VIDEO_DURATION,
    KLINGAI_POLLING_INTERVAL,
    KLINGAI_TASK_TIMEOUT,
)

logger = logging.getLogger(__name__)

OMNI_VIDEO_ENDPOINT = "/v1/videos/omni-video"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {KLINGAI_API_KEY}",
        "Content-Type": "application/json",
    }


async def create_video_task(image_url: str, prompt: str) -> str:
    """Create a video generation task in KlingAI.

    Args:
        image_url: URL of the product image (used as first frame).
        prompt: The video generation prompt.

    Returns:
        The KlingAI task_id.

    Raises:
        aiohttp.ClientError: On HTTP errors.
        ValueError: If the API response is unexpected.
    """
    url = f"{KLINGAI_API_URL}{OMNI_VIDEO_ENDPOINT}"

    payload = {
        "model_name": "kling-video-o1",
        "prompt": prompt,
        "image_list": [
            {
                "image_url": image_url,
                "type": "first_frame",
            }
        ],
        "mode": KLINGAI_MODE,
        "aspect_ratio": KLINGAI_ASPECT_RATIO,
        "duration": KLINGAI_VIDEO_DURATION,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        # Rate limited — exponential backoff
                        wait = (2 ** attempt) * 5
                        logger.warning(
                            f"KlingAI rate limited (429), retrying in {wait}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(wait)
                        continue
                    if resp.status >= 500:
                        logger.warning(
                            f"KlingAI server error ({resp.status}), "
                            f"retrying in 60s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(60)
                        continue

                    resp.raise_for_status()
                    data = await resp.json()

            if data.get("code") != 0:
                raise ValueError(
                    f"KlingAI error: code={data.get('code')}, "
                    f"message={data.get('message')}"
                )

            task_id = data["data"]["task_id"]
            logger.info(f"Created KlingAI task: {task_id}")
            return task_id

        except aiohttp.ClientError as e:
            if attempt == max_retries - 1:
                logger.error(f"KlingAI create task failed after {max_retries} retries: {e}")
                raise
            logger.warning(f"KlingAI request error: {e}, retrying...")
            await asyncio.sleep(5)

    raise RuntimeError("KlingAI create_video_task exhausted all retries")


async def get_task_status(task_id: str) -> dict:
    """Query the status of a KlingAI video generation task.

    Returns:
        Dict with keys: task_id, status, video_url (if succeed), error (if failed).
    """
    url = f"{KLINGAI_API_URL}{OMNI_VIDEO_ENDPOINT}/{task_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        if data.get("code") != 0:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": data.get("message", "Unknown error"),
            }

        task_data = data["data"]
        status = task_data.get("task_status", "unknown")

        result = {
            "task_id": task_id,
            "status": status,
        }

        if status == "succeed":
            videos = task_data.get("task_result", {}).get("videos", [])
            if videos:
                result["video_url"] = videos[0].get("url", "")
                result["video_id"] = videos[0].get("id", "")
                result["duration"] = videos[0].get("duration", "")
        elif status == "failed":
            result["error"] = task_data.get("task_status_msg", "Generation failed")

        return result

    except aiohttp.ClientError as e:
        logger.error(f"Error querying KlingAI task {task_id}: {e}")
        return {"task_id": task_id, "status": "error", "error": str(e)}


async def poll_task_until_done(task_id: str, timeout: int = None) -> dict:
    """Poll a KlingAI task until it succeeds, fails, or times out.

    Args:
        task_id: The KlingAI task ID.
        timeout: Max seconds to wait (default from config).

    Returns:
        Dict with status and video_url (if succeed).
    """
    if timeout is None:
        timeout = KLINGAI_TASK_TIMEOUT

    elapsed = 0
    while elapsed < timeout:
        result = await get_task_status(task_id)
        status = result.get("status")

        if status == "succeed":
            logger.info(f"KlingAI task {task_id} succeeded")
            return result
        elif status == "failed":
            logger.warning(f"KlingAI task {task_id} failed: {result.get('error')}")
            return result
        elif status == "error":
            logger.warning(f"Error polling task {task_id}, will retry...")

        await asyncio.sleep(KLINGAI_POLLING_INTERVAL)
        elapsed += KLINGAI_POLLING_INTERVAL

    logger.error(f"KlingAI task {task_id} timed out after {timeout}s")
    return {"task_id": task_id, "status": "failed", "error": "Timeout"}


async def generate_video_for_product(product: dict, prompt: str) -> dict:
    """High-level method: create task → wait for result.

    Args:
        product: Product dict with image_url.
        prompt: The KlingAI prompt.

    Returns:
        Dict with task_id, video_url, status.
    """
    image_url = product.get("image_url")
    if not image_url:
        return {"task_id": None, "status": "failed", "error": "No image URL"}

    task_id = await create_video_task(image_url, prompt)
    result = await poll_task_until_done(task_id)
    result["task_id"] = task_id
    return result


async def download_video(video_url: str, dest_path: str) -> str:
    """Download a video from KlingAI to a local file.

    Args:
        video_url: The URL of the generated video.
        dest_path: Local file path to save to.

    Returns:
        The dest_path on success.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                video_url, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
        logger.info(f"Downloaded video to {dest_path}")
        return dest_path
    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        raise
