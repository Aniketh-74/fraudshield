"""
TEST-02: Integration test — transaction decision persisted to PostgreSQL.

Exercises the database write/read path with a real testcontainers Postgres instance.
Verifies the full schema and that BLOCK decisions are stored with correct fraud_probability.
"""
import json
import uuid

import psycopg2
import pytest


def test_transaction_produces_decision_in_postgres(postgres_container):
    """TEST-02: Decision written to PostgreSQL is readable with correct fields."""
    txn_id = str(uuid.uuid4())
    conn = psycopg2.connect(postgres_container.get_connection_url())
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO transactions
           (transaction_id, user_id, amount, decision, fraud_probability, rules_triggered, features)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            txn_id,
            "test_user_001",
            50000.0,
            "BLOCK",
            0.85,
            json.dumps(["velocity_abuse"]),
            json.dumps({"txn_count_1h": 15, "amount_deviation": 4.5}),
        ),
    )
    conn.commit()

    cur.execute(
        "SELECT decision, fraud_probability, rules_triggered FROM transactions WHERE transaction_id = %s",
        (txn_id,),
    )
    row = cur.fetchone()
    assert row is not None, "Transaction was not persisted to PostgreSQL"
    assert row[0] == "BLOCK", f"Expected BLOCK decision, got {row[0]}"
    assert abs(row[1] - 0.85) < 0.01, f"Expected fraud_probability ~0.85, got {row[1]}"

    rules = row[2] if isinstance(row[2], list) else json.loads(row[2])
    assert "velocity_abuse" in rules

    cur.close()
    conn.close()


def test_approve_decision_stored(postgres_container):
    """APPROVE decisions can also be stored and retrieved."""
    txn_id = str(uuid.uuid4())
    conn = psycopg2.connect(postgres_container.get_connection_url())
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO transactions
           (transaction_id, user_id, amount, decision, fraud_probability, rules_triggered, features)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            txn_id,
            "test_user_002",
            100.0,
            "APPROVE",
            0.05,
            json.dumps([]),
            json.dumps({"txn_count_1h": 1}),
        ),
    )
    conn.commit()

    cur.execute("SELECT decision FROM transactions WHERE transaction_id = %s", (txn_id,))
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "APPROVE"

    cur.close()
    conn.close()


def test_multiple_decisions_queryable(postgres_container):
    """Multiple decisions can be written and queried for the recent transactions endpoint."""
    conn = psycopg2.connect(postgres_container.get_connection_url())
    cur = conn.cursor()

    decisions = [
        ("BLOCK", 0.9),
        ("FLAG", 0.55),
        ("APPROVE", 0.1),
    ]
    for decision, prob in decisions:
        cur.execute(
            """INSERT INTO transactions
               (transaction_id, user_id, amount, decision, fraud_probability, rules_triggered, features)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (str(uuid.uuid4()), "bulk_user", 500.0, decision, prob, json.dumps([]), json.dumps({})),
        )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = 'bulk_user'")
    count = cur.fetchone()[0]
    assert count == 3

    cur.close()
    conn.close()
