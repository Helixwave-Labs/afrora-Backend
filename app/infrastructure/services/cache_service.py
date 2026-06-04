import json
import logging
from typing import Any, Optional
from fastapi import Request

logger = logging.getLogger(__name__)

async def get_cached_data(request: Request, key: str) -> Optional[Any]:
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
    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        return
    try:
        serialized_data = json.dumps(data)
        await redis_client.setex(key, expire_seconds, serialized_data)
    except Exception as e:
        logger.error(f"Redis cache SET failed for key {key}: {e}")

async def delete_cache_pattern(request: Request, pattern: str):
    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        return
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await redis_client.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Redis cache DELETE matching pattern {pattern} failed: {e}")
