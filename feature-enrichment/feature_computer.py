"""
feature_computer.py — Compute real-time features per transaction.

Supports two feature modes (controlled by FEATURE_MODE env var):
  - "simulator" (default): original 14-feature set with geo/merchant features
  - "ieee-cis": 30-feature set matching IEEE-CIS training (no geo, adds card/C/D/V)

The mode must match the model in training/models/feature_order.json.

=== simulator mode (14 features) ===
    txn_count_1h, txn_count_6h, txn_count_24h,
    avg_amount_7d, amount_deviation, time_since_last_txn_seconds,
    unique_merchants_24h, max_amount_24h, is_new_merchant,
    hour_of_day, is_weekend, geo_distance_km, geo_velocity_kmh,
    merchant_category_enc

=== ieee-cis mode (30 features) ===
    hour_of_day, day_of_week, is_weekend,
    TransactionAmt, amt_log, amt_to_card1_mean_ratio,
    card1, card2_filled, card4_enc, card6_enc,
    addr1_enc, p_email_enc, dist1_filled,
    C1, C2, C5, C6, C13, C14,
    D1_filled, D2_filled, D15_filled,
    M4_enc, M6_enc,
    V12, V37, V58, V94, V130, V307, V308, V317
"""
import json
import math
import os
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import redis
import structlog

log = structlog.get_logger(__name__)

FEATURE_MODE = os.environ.get("FEATURE_MODE", "simulator").lower()

# ── Simulator mode: original encodings ────────────────────────────────────────
MERCHANT_CATEGORY_MAP: dict[str, int] = {
    "groceries": 0,
    "food": 1,
    "electronics": 2,
    "travel": 3,
    "entertainment": 4,
    "transfers": 5,
}

# ── IEEE-CIS mode: categorical encodings (must match features_ieee.py) ────────
CARD4_MAP  = {"visa": 0, "mastercard": 1, "american express": 2, "discover": 3}
CARD6_MAP  = {"debit": 0, "credit": 1, "debit or credit": 2, "charge card": 3}
M4_MAP     = {"M0": 0, "M1": 1, "M2": 2}
M6_MAP     = {"F": 0, "T": 1}

# TTL constants (simulator mode)
_TTL_VELOCITY_SECONDS = 3600
_TTL_VELOCITY_WINDOW_SECONDS = 90000  # 25 hours
_TTL_PROFILE_SECONDS = 604800         # 7 days
_GEO_VEL_CAP_KMH = 2000.0

# TTL for ieee-cis card1 running mean (30 days)
_TTL_CARD1_PROFILE_SECONDS = 2592000


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance — used in simulator mode only."""
    R = 6371.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ── Category-mappings loader (ieee-cis mode) ──────────────────────────────────
_category_mappings_cache: dict | None = None

def _load_category_mappings() -> dict:
    """Load addr1 and P_emaildomain mappings from category_mappings.json (ieee-cis mode)."""
    global _category_mappings_cache
    if _category_mappings_cache is not None:
        return _category_mappings_cache
    mappings_path = os.environ.get("CATEGORY_MAPPINGS_PATH", "/models/category_mappings.json")
    try:
        with open(mappings_path) as f:
            _category_mappings_cache = json.load(f)
    except FileNotFoundError:
        log.warning("feature_computer.category_mappings_not_found", path=mappings_path)
        _category_mappings_cache = {}
    return _category_mappings_cache


def _enc(value, mapping: dict) -> int:
    """Label-encode a single value using a mapping dict. Unknown → -1."""
    if value is None:
        return -1
    return mapping.get(str(value), -1)


# ──────────────────────────────────────────────────────────────────────────────
# Public API (used by kafka_consumer.py)
# ──────────────────────────────────────────────────────────────────────────────

def read_user_state(r: redis.Redis, user_id: str) -> dict:
    """
    Read prior state from Redis. Returns empty dict {} for new users.
    Works for both simulator and ieee-cis modes (key namespacing is the same).
    """
    velocity_raw = r.hgetall(f"user:{user_id}:velocity") or {}
    profile_raw  = r.hgetall(f"user:{user_id}:profile")  or {}
    combined = {}
    for raw in (velocity_raw, profile_raw):
        for k, v in raw.items():
            combined[k.decode("utf-8")] = v.decode("utf-8")
    return combined


def compute_and_write(r: redis.Redis, txn: dict, prior_state: dict) -> dict:
    """
    Compute all features for the current transaction, write new state to Redis,
    and return the feature dict.

    Dispatches to _compute_simulator or _compute_ieee_cis based on FEATURE_MODE.
    """
    if FEATURE_MODE == "ieee-cis":
        return _compute_ieee_cis(r, txn, prior_state)
    return _compute_simulator(r, txn, prior_state)


# ──────────────────────────────────────────────────────────────────────────────
# Simulator mode (original 14 features)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_simulator(r: redis.Redis, txn: dict, prior_state: dict) -> dict:
    """Original 14-feature computation for simulator-trained model."""
    user_id: str  = txn["user_id"]
    amount: float = float(txn["amount"])
    merchant_id: str = txn["merchant_id"]
    merchant_category: str = txn["merchant_category"]
    lat: float = float(txn["latitude"])
    lng: float = float(txn["longitude"])
    txn_id: str = txn["transaction_id"]

    ts_str: str = txn["timestamp"]
    ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    current_epoch: float = ts_dt.timestamp()

    ist_dt = ts_dt.astimezone(ZoneInfo("Asia/Kolkata"))
    hour_of_day: int = ist_dt.hour
    is_weekend: int = 1 if ist_dt.weekday() in (5, 6) else 0

    merchant_category_enc: int = MERCHANT_CATEGORY_MAP.get(merchant_category, -1)

    is_first_txn: bool = not prior_state

    if is_first_txn or "last_ts_epoch" not in prior_state:
        time_since_last = -1.0
    else:
        time_since_last = current_epoch - float(prior_state["last_ts_epoch"])

    if is_first_txn or "last_lat" not in prior_state:
        geo_distance_km = 0.0
        geo_velocity_kmh = 0.0
    else:
        last_lat = float(prior_state["last_lat"])
        last_lng = float(prior_state["last_lng"])
        geo_distance_km = _haversine_km(last_lat, last_lng, lat, lng)
        if time_since_last > 0:
            raw_vel = geo_distance_km / (time_since_last / 3600.0)
            geo_velocity_kmh = min(raw_vel, _GEO_VEL_CAP_KMH)
        else:
            geo_velocity_kmh = 0.0

    txn_ts_key  = f"user:{user_id}:txn_ts"
    amounts_key = f"user:{user_id}:amounts_24h"
    merchants_key = f"user:{user_id}:merchants_24h"
    seen_key    = f"user:{user_id}:seen_merchants"

    cutoff_1h  = current_epoch - 3600
    cutoff_6h  = current_epoch - 21600
    cutoff_24h = current_epoch - 86400
    cutoff_7d  = current_epoch - 604800

    r.zremrangebyscore(txn_ts_key, 0, cutoff_24h)
    txn_count_1h  = int(r.zcount(txn_ts_key, cutoff_1h, "+inf"))
    txn_count_6h  = int(r.zcount(txn_ts_key, cutoff_6h, "+inf"))
    txn_count_24h = int(r.zcount(txn_ts_key, cutoff_24h, "+inf"))

    r.zremrangebyscore(amounts_key, 0, cutoff_24h)
    amounts_in_24h_raw = r.zrangebyscore(amounts_key, cutoff_24h, "+inf")
    if amounts_in_24h_raw:
        max_amount_24h = max(
            float(m.decode("utf-8").split(":", 1)[1]) for m in amounts_in_24h_raw
        )
    else:
        max_amount_24h = 0.0

    r.zremrangebyscore(merchants_key, 0, cutoff_24h)
    merchants_in_24h = r.zrangebyscore(merchants_key, cutoff_24h, "+inf")
    unique_merchants_24h = len(set(m.decode("utf-8") for m in merchants_in_24h))

    was_seen = bool(r.sismember(seen_key, merchant_id))
    is_new_merchant: int = 0 if was_seen else 1

    if prior_state and "amount_count_7d" in prior_state:
        prior_count = int(prior_state.get("amount_count_7d", 0))
        prior_sum   = float(prior_state.get("amount_sum_7d", 0.0))
        avg_amount_7d = prior_sum / prior_count if prior_count > 0 else amount
    else:
        prior_count = 0
        prior_sum   = 0.0
        avg_amount_7d = amount

    r.zremrangebyscore(amounts_key, 0, cutoff_7d)
    amounts_7d_raw = r.zrangebyscore(amounts_key, cutoff_7d, "+inf")
    if len(amounts_7d_raw) >= 2:
        amounts_7d = [float(m.decode("utf-8").split(":", 1)[1]) for m in amounts_7d_raw]
        std_7d = statistics.stdev(amounts_7d)
        amount_deviation = (amount - avg_amount_7d) / std_7d if std_7d > 0 else 0.0
    else:
        amount_deviation = 0.0

    r.zadd(txn_ts_key, {txn_id: current_epoch})
    r.zadd(amounts_key, {f"{current_epoch}:{amount}": current_epoch})
    r.zadd(merchants_key, {merchant_id: current_epoch})
    r.sadd(seen_key, merchant_id)

    r.expire(txn_ts_key,   _TTL_VELOCITY_WINDOW_SECONDS, nx=True)
    r.expire(amounts_key,  _TTL_VELOCITY_WINDOW_SECONDS, nx=True)
    r.expire(merchants_key, _TTL_VELOCITY_WINDOW_SECONDS, nx=True)

    new_velocity = {
        "txn_count_1h": str(txn_count_1h),
        "txn_count_6h": str(txn_count_6h),
        "txn_count_24h": str(txn_count_24h),
        "unique_merchants_24h": str(unique_merchants_24h),
        "max_amount_24h": str(max_amount_24h),
    }
    r.hset(f"user:{user_id}:velocity", mapping=new_velocity)
    r.expire(f"user:{user_id}:velocity", _TTL_VELOCITY_SECONDS, nx=True)

    new_amount_count = prior_count + 1
    new_amount_sum   = prior_sum + amount
    new_profile = {
        "last_ts_epoch":    str(current_epoch),
        "last_lat":         str(lat),
        "last_lng":         str(lng),
        "avg_amount_7d":    str(new_amount_sum / new_amount_count),
        "amount_sum_7d":    str(new_amount_sum),
        "amount_count_7d":  str(new_amount_count),
    }
    r.hset(f"user:{user_id}:profile", mapping=new_profile)
    r.expire(f"user:{user_id}:profile", _TTL_PROFILE_SECONDS, nx=True)

    return {
        "txn_count_1h":              txn_count_1h,
        "txn_count_6h":              txn_count_6h,
        "txn_count_24h":             txn_count_24h,
        "avg_amount_7d":             avg_amount_7d,
        "amount_deviation":          amount_deviation,
        "time_since_last_txn_seconds": time_since_last,
        "unique_merchants_24h":      unique_merchants_24h,
        "max_amount_24h":            max_amount_24h,
        "is_new_merchant":           is_new_merchant,
        "hour_of_day":               hour_of_day,
        "is_weekend":                is_weekend,
        "geo_distance_km":           geo_distance_km,
        "geo_velocity_kmh":          geo_velocity_kmh,
        "merchant_category_enc":     merchant_category_enc,
    }


# ──────────────────────────────────────────────────────────────────────────────
# IEEE-CIS mode (30 features)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_ieee_cis(r: redis.Redis, txn: dict, prior_state: dict) -> dict:
    """
    30-feature computation matching IEEE-CIS trained model.

    Expected txn fields (from simulator enriched with card/email metadata, or
    from a real payment gateway):
        transaction_id, timestamp, amount, card1, card2, card4, card6,
        addr1, P_emaildomain, dist1, C1..C6..C13..C14, D1..D2..D15,
        M4, M6, V12, V37, V58, V94, V130, V307, V308, V317

    Fields not available → use sentinel values (same as training NaN-fill strategy).

    Redis state tracked:
        card1:{card1}:profile  — running mean/count of amounts for amt_to_card1_mean_ratio
    """
    mappings = _load_category_mappings()

    amount: float = float(txn.get("amount", txn.get("TransactionAmt", 0.0)))
    card1:  int   = int(txn.get("card1", 0))
    card2:  float = float(txn.get("card2", 0.0)) if txn.get("card2") is not None else 0.0
    card4:  str   = str(txn.get("card4", "")).lower().strip()
    card6:  str   = str(txn.get("card6", "")).lower().strip()
    addr1:  str   = str(int(txn.get("addr1", -1))) if txn.get("addr1") is not None else "-1"
    p_email: str  = str(txn.get("P_emaildomain", "unknown")).lower().strip()
    dist1:  float = float(txn.get("dist1", 0.0)) if txn.get("dist1") is not None else 0.0

    # C-features (count features — 0 if not present)
    def _c(name: str) -> float:
        return float(txn.get(name, 0.0)) if txn.get(name) is not None else 0.0

    C1, C2, C5, C6, C13, C14 = _c("C1"), _c("C2"), _c("C5"), _c("C6"), _c("C13"), _c("C14")

    # D-features (-1 sentinel if missing)
    def _d(name: str, sentinel: float = -1.0) -> float:
        v = txn.get(name)
        return float(v) if v is not None else sentinel

    D1  = _d("D1",  sentinel=0.0)   # card age — 0 = new card
    D2  = _d("D2",  sentinel=-1.0)  # days since last txn
    D15 = _d("D15", sentinel=-1.0)  # days since last addr change

    # M-flags
    M4 = str(txn.get("M4", "")) if txn.get("M4") is not None else ""
    M6 = str(txn.get("M6", "")) if txn.get("M6") is not None else ""

    # V-features (fill with 0 if missing)
    v_vals = {}
    for v in ["V12", "V37", "V58", "V94", "V130", "V307", "V308", "V317"]:
        val = txn.get(v)
        v_vals[v] = float(val) if val is not None else 0.0

    # Temporal (use IST for consistency with simulator mode)
    ts_str = txn.get("timestamp", txn.get("TransactionDT", ""))
    if isinstance(ts_str, (int, float)):
        # TransactionDT (seconds offset) — derive hour/day
        dt_secs = int(ts_str)
        hour_of_day = (dt_secs // 3600) % 24
        day_of_week = (dt_secs // 86400) % 7
    else:
        ts_dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        ist_dt = ts_dt.astimezone(ZoneInfo("Asia/Kolkata"))
        hour_of_day = ist_dt.hour
        day_of_week = ist_dt.weekday()
    is_weekend = 1 if day_of_week in (5, 6) else 0

    # Amount features
    import math as _math
    amt_log = _math.log1p(amount)

    # amt_to_card1_mean_ratio — running mean per card1 in Redis
    card1_profile_key = f"card1:{card1}:profile"
    card1_raw = r.hgetall(card1_profile_key) or {}
    card1_state = {k.decode("utf-8"): v.decode("utf-8") for k, v in card1_raw.items()}

    if card1_state and "amt_count" in card1_state:
        c1_count = int(card1_state["amt_count"])
        c1_sum   = float(card1_state["amt_sum"])
        card1_mean = c1_sum / c1_count
    else:
        c1_count = 0
        c1_sum   = 0.0
        card1_mean = amount  # neutral: ratio = 1.0 for first transaction

    amt_to_card1_mean_ratio = amount / (card1_mean + 1e-9)

    # Update card1 running mean
    new_c1_count = c1_count + 1
    new_c1_sum   = c1_sum + amount
    r.hset(card1_profile_key, mapping={
        "amt_count": str(new_c1_count),
        "amt_sum":   str(new_c1_sum),
    })
    r.expire(card1_profile_key, _TTL_CARD1_PROFILE_SECONDS, nx=True)

    # Categorical encodings
    card4_enc = _enc(card4, CARD4_MAP)
    card6_enc = _enc(card6, CARD6_MAP)
    m4_enc    = _enc(M4, M4_MAP)
    m6_enc    = _enc(M6, M6_MAP)

    # addr1 and P_emaildomain use training-time label encodings
    addr1_mapping   = mappings.get("addr1", {})
    p_email_mapping = mappings.get("P_emaildomain", {})
    addr1_enc  = _enc(addr1, addr1_mapping)
    p_email_enc = _enc(p_email, p_email_mapping)

    return {
        "hour_of_day":              hour_of_day,
        "day_of_week":              day_of_week,
        "is_weekend":               is_weekend,
        "TransactionAmt":           amount,
        "amt_log":                  amt_log,
        "amt_to_card1_mean_ratio":  amt_to_card1_mean_ratio,
        "card1":                    card1,
        "card2_filled":             card2,
        "card4_enc":                card4_enc,
        "card6_enc":                card6_enc,
        "addr1_enc":                addr1_enc,
        "p_email_enc":              p_email_enc,
        "dist1_filled":             dist1,
        "C1": C1, "C2": C2, "C5": C5, "C6": C6, "C13": C13, "C14": C14,
        "D1_filled":  D1,
        "D2_filled":  D2,
        "D15_filled": D15,
        "M4_enc": m4_enc,
        "M6_enc": m6_enc,
        **v_vals,
    }
