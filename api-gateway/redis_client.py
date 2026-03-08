"""
redis_client.py — Minimal async Redis client for API Gateway.
"""
import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)


async def create_redis(url: str):
    """Create and return an async Redis connection from the given URL."""
    r = aioredis.from_url(url, decode_responses=True)
    log.info("redis_client_created", url=url)
    return r


async def close_redis(r) -> None:
    """Close the Redis connection."""
    await r.aclose()
    log.info("redis_client_closed")


async def get_user_features(redis, user_id: str) -> dict:
    """
    Stub: retrieve user feature profile from Redis hash.
    Used for future feature context reads (API-06 requirement).
    Returns empty dict if key not found.
    """
    data = await redis.hgetall(f"user:{user_id}:profile")
    if not data:
        return {}
    return data
