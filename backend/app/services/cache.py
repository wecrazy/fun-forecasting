"""
services/cache.py — Redis helpers using aioredis (async).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def publish_progress(job_id: str, event: dict[str, Any]) -> None:
    """Publish a progress event to the job's Redis pub/sub channel."""
    channel = f"job:{job_id}:progress"
    try:
        await get_redis().publish(channel, json.dumps(event))
    except Exception as exc:
        logger.warning("Failed to publish progress for job %s: %s", job_id, exc)


async def subscribe_progress(job_id: str):
    """
    Async generator that yields raw JSON strings from the job progress channel.
    Caller is responsible for closing the pubsub connection.
    """
    channel = f"job:{job_id}:progress"
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield message["data"]
    finally:
        await pubsub.unsubscribe(channel)
        await client.aclose()


async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    """Store a JSON-serialisable value in Redis with a TTL."""
    try:
        await get_redis().setex(key, ttl, json.dumps(value))
    except Exception as exc:
        logger.warning("cache_set failed for key %s: %s", key, exc)


async def cache_get(key: str) -> Any | None:
    """Retrieve a value from Redis; returns None on miss or error."""
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.warning("cache_get failed for key %s: %s", key, exc)
        return None
