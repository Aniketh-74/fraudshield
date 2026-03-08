"""
redis_client.py — Redis connection builder with startup retry.

Functions:
    build_redis_client  — Connect to Redis with exponential backoff retry (3x).
                          Raises RuntimeError on exhaustion (so Docker restarts the service).
"""
import time
import redis
import structlog
import config

log = structlog.get_logger(__name__)


def build_redis_client() -> redis.Redis:
    """
    Create and verify a Redis client with retry.

    Uses redis.from_url() for connection-string based config. Calls r.ping()
    to force an actual connection attempt (unlike constructor which is lazy).

    Retry: up to REDIS_RETRY_ATTEMPTS times, exponential backoff:
        attempt 1: wait 1s, attempt 2: wait 2s, attempt 3: wait 4s

    Raises:
        RuntimeError: if all attempts exhausted (let Docker/K8s restart).
    """
    for attempt in range(1, config.REDIS_RETRY_ATTEMPTS + 1):
        try:
            r = redis.from_url(config.REDIS_URL, decode_responses=False)
            r.ping()
            log.info("redis_connected", attempt=attempt, url=config.REDIS_URL)
            return r
        except redis.RedisError as e:
            log.warning(
                "redis_unavailable",
                attempt=attempt,
                max_attempts=config.REDIS_RETRY_ATTEMPTS,
                error=str(e),
            )
            if attempt < config.REDIS_RETRY_ATTEMPTS:
                wait = config.REDIS_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(wait)

    raise RuntimeError(
        f"Redis connection exhausted after {config.REDIS_RETRY_ATTEMPTS} attempts. "
        f"URL: {config.REDIS_URL}"
    )
