import json
import logging
from typing import Any, Optional
from fastapi import Request

logger = logging.getLogger(__name__)

async def get_cached_data(request: Request, key: str) -> Optional[Any]:
    """
    Retrieve serialized JSON data from Redis cache.
    """
    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        return None
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Redis cache GET failed for key {key}: {e}")
    return None

async def set_cached_data(request: Request, key: str, data: Any, expire_seconds: int = 300):
    """
    Store serialized JSON data into Redis cache with an expiration time.
    """
    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        return
    try:
        serialized_data = json.dumps(data)
        await redis_client.setex(key, expire_seconds, serialized_data)
    except Exception as e:
        logger.error(f"Redis cache SET failed for key {key}: {e}")

async def delete_cache_pattern(request: Request, pattern: str):
    """
    Delete keys from Redis matching a glob pattern (e.g., 'products:list:*').
    """
    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        return
    try:
        # Note: keys() is an O(N) operation. In production environments with massive
        # datasets, using SCAN is preferred. Here we execute keys matching safely.
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis cache DELETE matching pattern {pattern} failed: {e}")
