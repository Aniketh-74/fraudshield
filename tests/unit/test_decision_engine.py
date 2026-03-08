"""
Unit tests for decision-engine service.

Tests the business rules evaluation and apply_decision_matrix function.
RulesEngine is tested by loading the actual rules.yaml from the source tree.
apply_decision_matrix is tested directly — it is a pure function.

No Kafka, Postgres, Redis, or ML scorer required.
"""
import sys
import os
import tempfile

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../decision-engine"))

from rules_engine import RulesEngine
from kafka_consumer import apply_decision_matrix

# Path to the actual rules.yaml used in production
_RULES_YAML = os.path.join(os.path.dirname(__file__), "../../decision-engine/rules.yaml")


def _make_engine() -> RulesEngine:
    """Return a RulesEngine loaded from the real rules.yaml."""
    return RulesEngine(_RULES_YAML)


# ---------------------------------------------------------------------------
# Business rule: impossible_travel (geo_velocity_kmh > 500 → fires)
# ---------------------------------------------------------------------------

def test_impossible_travel_rule_triggers_when_velocity_above_500():
    """geo_velocity_kmh > 500 must cause impossible_travel rule to fire."""
    engine = _make_engine()
    features = {"geo_velocity_kmh": 600.0}
    fired = engine.evaluate(features)
    assert "impossible_travel" in fired, f"Expected impossible_travel, got: {fired}"


def test_impossible_travel_rule_does_not_trigger_below_threshold():
    """geo_velocity_kmh <= 500 must NOT cause impossible_travel rule to fire."""
    engine = _make_engine()
    features = {"geo_velocity_kmh": 400.0}
    fired = engine.evaluate(features)
    assert "impossible_travel" not in fired, f"Unexpected impossible_travel with vel=400"


# ---------------------------------------------------------------------------
# Business rule: velocity_abuse (txn_count_1h > 10 → fires)
# ---------------------------------------------------------------------------

def test_velocity_abuse_rule_triggers_when_count_above_10():
    """txn_count_1h > 10 must cause velocity_abuse rule to fire."""
    engine = _make_engine()
    features = {"txn_count_1h": 15.0}
    fired = engine.evaluate(features)
    assert "velocity_abuse" in fired, f"Expected velocity_abuse, got: {fired}"


def test_velocity_abuse_rule_does_not_trigger_at_10():
    """txn_count_1h == 10 must NOT trigger velocity_abuse (rule uses strict >)."""
    engine = _make_engine()
    features = {"txn_count_1h": 10.0}
    fired = engine.evaluate(features)
    assert "velocity_abuse" not in fired, f"Unexpected velocity_abuse at count=10"


# ---------------------------------------------------------------------------
# Business rule: midnight_high_value (1AM-5AM IST + amount > 10000 → fires)
# ---------------------------------------------------------------------------

def test_midnight_high_value_triggers_at_1am_high_amount():
    """hour_of_day=1 (1AM IST) + amount=15000 must trigger midnight_high_value."""
    engine = _make_engine()
    features = {"hour_of_day": 1.0, "amount": 15000.0}
    fired = engine.evaluate(features)
    assert "midnight_high_value" in fired, f"Expected midnight_high_value, got: {fired}"


def test_midnight_high_value_triggers_at_4am_high_amount():
    """hour_of_day=4 (4AM IST) + amount=20000 must trigger midnight_high_value."""
    engine = _make_engine()
    features = {"hour_of_day": 4.0, "amount": 20000.0}
    fired = engine.evaluate(features)
    assert "midnight_high_value" in fired, f"Expected midnight_high_value, got: {fired}"


def test_midnight_high_value_does_not_trigger_at_noon():
    """hour_of_day=12 (noon) must NOT trigger midnight_high_value even with high amount."""
    engine = _make_engine()
    features = {"hour_of_day": 12.0, "amount": 50000.0}
    fired = engine.evaluate(features)
    assert "midnight_high_value" not in fired, "midnight_high_value should not fire at noon"


def test_midnight_high_value_does_not_trigger_low_amount_at_midnight():
    """hour_of_day=2 with amount=500 (below 10000) must NOT trigger rule."""
    engine = _make_engine()
    features = {"hour_of_day": 2.0, "amount": 500.0}
    fired = engine.evaluate(features)
    assert "midnight_high_value" not in fired, "midnight_high_value should not fire with low amount"


# ---------------------------------------------------------------------------
# Business rule: amount_spike (amount_deviation > 3.0 → fires)
# ---------------------------------------------------------------------------

def test_amount_spike_triggers_when_deviation_above_3():
    """amount_deviation > 3.0 must cause amount_spike rule to fire."""
    engine = _make_engine()
    features = {"amount_deviation": 4.5}
    fired = engine.evaluate(features)
    assert "amount_spike" in fired, f"Expected amount_spike, got: {fired}"


def test_amount_spike_does_not_trigger_at_exactly_3():
    """amount_deviation == 3.0 must NOT trigger amount_spike (strict >)."""
    engine = _make_engine()
    features = {"amount_deviation": 3.0}
    fired = engine.evaluate(features)
    assert "amount_spike" not in fired, "amount_spike should not fire at exactly 3.0"


# ---------------------------------------------------------------------------
# Multiple rules can fire simultaneously
# ---------------------------------------------------------------------------

def test_multiple_rules_fire_simultaneously():
    """Both velocity_abuse and amount_spike can fire at the same time."""
    engine = _make_engine()
    features = {
        "txn_count_1h": 15.0,
        "amount_deviation": 5.0,
    }
    fired = engine.evaluate(features)
    assert "velocity_abuse" in fired
    assert "amount_spike" in fired


# ---------------------------------------------------------------------------
# Decision matrix tests (pure function — no engine needed)
# ---------------------------------------------------------------------------

def test_decision_matrix_high_score_any_rule_blocks():
    """ML HIGH (>0.7) + any rule fired → BLOCK."""
    decision = apply_decision_matrix("HIGH", ["velocity_abuse"])
    assert decision == "BLOCK", f"Expected BLOCK, got {decision}"


def test_decision_matrix_high_score_multiple_rules_blocks():
    """ML HIGH + multiple rules fired → BLOCK."""
    decision = apply_decision_matrix("HIGH", ["impossible_travel", "amount_spike"])
    assert decision == "BLOCK", f"Expected BLOCK, got {decision}"


def test_decision_matrix_high_score_no_rule_flags():
    """ML HIGH (>0.7) + no rule fired → FLAG."""
    decision = apply_decision_matrix("HIGH", [])
    assert decision == "FLAG", f"Expected FLAG, got {decision}"


def test_decision_matrix_medium_score_any_rule_flags():
    """ML MEDIUM (0.3-0.7) + any rule fired → FLAG."""
    decision = apply_decision_matrix("MEDIUM", ["velocity_abuse"])
    assert decision == "FLAG", f"Expected FLAG, got {decision}"


def test_decision_matrix_medium_score_no_rule_approves():
    """ML MEDIUM (0.3-0.7) + no rule fired → APPROVE."""
    decision = apply_decision_matrix("MEDIUM", [])
    assert decision == "APPROVE", f"Expected APPROVE, got {decision}"


def test_decision_matrix_low_score_no_rules_approves():
    """ML LOW (<0.3) + no rule fired → APPROVE."""
    decision = apply_decision_matrix("LOW", [])
    assert decision == "APPROVE", f"Expected APPROVE, got {decision}"


def test_decision_matrix_low_score_with_rules_still_approves():
    """ML LOW (<0.3) + rules fired → APPROVE (LOW always approves)."""
    decision = apply_decision_matrix("LOW", ["velocity_abuse", "amount_spike"])
    assert decision == "APPROVE", f"Expected APPROVE for LOW risk, got {decision}"


# ---------------------------------------------------------------------------
# RulesEngine: disabled rules are not evaluated
# ---------------------------------------------------------------------------

def test_disabled_rule_is_skipped():
    """A rule with enabled: false must not fire even when condition is met."""
    rules_config = {
        "rules": [
            {
                "name": "test_disabled_rule",
                "enabled": False,
                "action": "FLAG",
                "condition": {
                    "field": "geo_velocity_kmh",
                    "operator": ">",
                    "value": 0,
                },
            }
        ]
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(rules_config, f)
        tmp_path = f.name

    engine = RulesEngine(tmp_path)
    fired = engine.evaluate({"geo_velocity_kmh": 9999.0})
    assert "test_disabled_rule" not in fired, "Disabled rule must not fire"

    os.unlink(tmp_path)
