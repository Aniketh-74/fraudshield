"""
conftest.py — Session-scoped testcontainers fixtures for integration tests.

Provides real Postgres and Redis containers via testcontainers library.
Requires Docker to be running. These fixtures are NOT used by unit tests.

Fixtures:
    postgres_container  — session-scoped PostgresContainer with transactions table
    redis_container     — session-scoped RedisContainer
    flush_redis         — autouse fixture: flushes Redis between tests
    clean_postgres      — autouse fixture: deletes all rows between tests
"""
import pytest
import psycopg2
import redis as redis_lib
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """
    Session-scoped PostgreSQL container.

    Spins up postgres:16-alpine once per test session, applies the
    transactions table schema, and yields the container for URL extraction.
    Container stops automatically after all session tests finish.
    """
    with PostgresContainer("postgres:16-alpine") as pg:
        conn = psycopg2.connect(pg.get_connection_url())
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id UUID PRIMARY KEY,
                user_id VARCHAR(50),
                amount DECIMAL(12,2),
                decision VARCHAR(20),
                fraud_probability FLOAT,
                rules_triggered JSONB,
                features JSONB,
                shap_values JSONB,
                reviewed_by VARCHAR(50),
                reviewed_at TIMESTAMP,
                review_outcome VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """
    Session-scoped Redis container.

    Spins up redis:7-alpine once per test session.
    Container stops automatically after all session tests finish.
    """
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(autouse=True)
def flush_redis(redis_container):
    """Flush all Redis keys between tests to prevent state leakage."""
    r = redis_lib.Redis.from_url(redis_container.get_connection_url())
    yield
    r.flushall()


@pytest.fixture(autouse=True)
def clean_postgres(postgres_container):
    """Delete all rows from the transactions table between tests."""
    conn = psycopg2.connect(postgres_container.get_connection_url())
    yield
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions")
    conn.commit()
    cur.close()
    conn.close()
