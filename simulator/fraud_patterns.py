"""
fraud_patterns.py — FraudInjector class with all 5 fraud pattern methods.

Patterns:
  1. rapid_fire       — 3+ transactions from same user within 60 seconds
  2. amount_spike     — amount > user avg_spend * 10x multiplier
  3. geo_velocity     — impossible travel speed between two cities
  4. unusual_merchant — grocery user spends ₹50k+ on electronics
  5. midnight_large   — ₹10k+ transaction between 1AM–5AM IST

Key design: single-threaded service, no locking required.
"""
import math
import random
from collections import deque
from datetime import datetime
from typing import Optional

import structlog

from cities import CITIES, CITY_NAMES

logger = structlog.get_logger(__name__)

EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Standalone math helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate great-circle distance between two points on Earth.
    Returns distance in kilometres.

    Verification: Mumbai (19.076, 72.877) to Bengaluru (12.972, 77.581)
    Expected: ~984 km
    """
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def geo_velocity_kmh(
    lat1: float, lng1: float, ts1: float,
    lat2: float, lng2: float, ts2: float,
) -> float:
    """Returns speed in km/h between two location+time observations."""
    distance_km = haversine_km(lat1, lng1, lat2, lng2)
    time_hours = abs(ts2 - ts1) / 3600.0
    if time_hours < 1e-6:
        return float("inf")
    return distance_km / time_hours


# ---------------------------------------------------------------------------
# FraudInjector
# ---------------------------------------------------------------------------

_PATTERNS = [
    "rapid_fire",
    "amount_spike",
    "geo_velocity",
    "unusual_merchant",
    "midnight_large",
]


class FraudInjector:
    """
    Decides whether and which fraud pattern to apply to a transaction.
    Called once per transaction in the main loop via try_inject_fraud().
    """

    def __init__(self, config, user_registry, merchant_registry, rng: random.Random) -> None:
        self.config = config
        self.user_registry = user_registry
        self.merchant_registry = merchant_registry
        self.rng = rng
        # Pending rapid-fire burst transactions (deque of base_txn dicts)
        self._pending_burst: deque = deque()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def try_inject_fraud(self, base_txn_fields: dict, now_utc: datetime) -> dict:
        """
        Decide whether to inject fraud into the transaction.

        Args:
            base_txn_fields: dict with all transaction fields except is_fraud
            now_utc: current UTC datetime

        Returns:
            Final transaction fields dict with is_fraud key set (bool).
        """
        user_id = base_txn_fields["user_id"]
        now_ts = now_utc.timestamp()
        state = self.user_registry.get_state(user_id)

        # Check cooldown — skip fraud for users recently burst-attacked
        if state.fraud_cooldown_until > now_ts:
            txn = dict(base_txn_fields)
            txn["is_fraud"] = False
            return txn

        # Decide whether to inject fraud at all
        if self.rng.random() >= self.config.FRAUD_RATE:
            txn = dict(base_txn_fields)
            txn["is_fraud"] = False
            return txn

        # Try patterns in shuffled order; fall through if a pattern returns None
        patterns = _PATTERNS[:]
        self.rng.shuffle(patterns)

        for pattern in patterns:
            result = self._attempt_pattern(pattern, base_txn_fields, now_utc, now_ts)
            if result is not None:
                logger.info(
                    "fraud_injected",
                    pattern=pattern,
                    user_id=user_id,
                    amount=result.get("amount"),
                )
                return result

        # All patterns returned None (e.g., no prior location for geo-velocity etc.)
        txn = dict(base_txn_fields)
        txn["is_fraud"] = False
        return txn

    def has_pending_burst(self) -> bool:
        """True if rapid-fire burst transactions are waiting to be emitted."""
        return len(self._pending_burst) > 0

    def pop_burst_txn(self) -> Optional[dict]:
        """Return the next burst transaction dict, or None if empty."""
        if self._pending_burst:
            return self._pending_burst.popleft()
        return None

    def clear_burst(self) -> None:
        """Clear any remaining pending burst transactions."""
        self._pending_burst.clear()

    # ------------------------------------------------------------------
    # Pattern dispatch
    # ------------------------------------------------------------------

    def _attempt_pattern(
        self, pattern: str, base_txn: dict, now_utc: datetime, now_ts: float
    ) -> Optional[dict]:
        user_id = base_txn["user_id"]

        if pattern == "rapid_fire":
            return self._inject_rapid_fire(user_id, base_txn, now_ts)
        elif pattern == "amount_spike":
            return self._inject_amount_spike(user_id, base_txn)
        elif pattern == "geo_velocity":
            return self._inject_geo_velocity(user_id, base_txn, now_ts)
        elif pattern == "unusual_merchant":
            return self._inject_unusual_merchant(user_id, base_txn)
        elif pattern == "midnight_large":
            return self._inject_midnight_large(base_txn, now_utc)
        return None

    # ------------------------------------------------------------------
    # Pattern 1: Rapid-Fire
    # ------------------------------------------------------------------

    def _inject_rapid_fire(self, user_id: str, base_txn: dict, now_ts: float) -> dict:
        """
        Marks this transaction as fraud and schedules 2 more rapid-fire txns.
        The main loop is responsible for checking has_pending_burst() and emitting them.
        After the burst, the user enters a 5-minute fraud cooldown.
        """
        txn = dict(base_txn)
        txn["is_fraud"] = True

        # Schedule 2 additional burst transactions (same user, same base shape)
        for _ in range(2):
            burst_txn = dict(base_txn)
            burst_txn["is_fraud"] = True
            self._pending_burst.append(burst_txn)

        # Set cooldown for 5 minutes after the burst
        state = self.user_registry.get_state(user_id)
        state.fraud_cooldown_until = now_ts + 300.0

        return txn

    # ------------------------------------------------------------------
    # Pattern 2: Amount Spike
    # ------------------------------------------------------------------

    def _inject_amount_spike(self, user_id: str, base_txn: dict) -> dict:
        """
        Forces amount = profile.avg_spend * AMOUNT_SPIKE_MULTIPLIER * uniform(1.0, 1.5).
        Uses the profile's startup avg_spend, NOT the current transaction amount.
        """
        profile = self.user_registry.get_profile(user_id)
        spike_amount = (
            profile.avg_spend
            * self.config.AMOUNT_SPIKE_MULTIPLIER
            * self.rng.uniform(1.0, 1.5)
        )
        txn = dict(base_txn)
        txn["amount"] = round(spike_amount, 2)
        txn["is_fraud"] = True
        return txn

    # ------------------------------------------------------------------
    # Pattern 3: Geo-Velocity
    # ------------------------------------------------------------------

    def _inject_geo_velocity(
        self, user_id: str, base_txn: dict, now_ts: float
    ) -> Optional[dict]:
        """
        Forces the transaction to a city far from the user's last known city.
        Returns None if no prior location or window elapsed.
        """
        state = self.user_registry.get_state(user_id)

        if state.last_lat is None or state.last_ts is None:
            logger.debug(
                "fraud_pattern_skipped",
                pattern="geo_velocity",
                reason="no_prior_location",
                user_id=user_id,
            )
            return None

        time_elapsed_minutes = (now_ts - state.last_ts) / 60.0
        if time_elapsed_minutes > self.config.GEO_VELOCITY_WINDOW_MINUTES:
            logger.debug(
                "fraud_pattern_skipped",
                pattern="geo_velocity",
                reason="window_elapsed",
                user_id=user_id,
                elapsed_minutes=round(time_elapsed_minutes, 1),
            )
            return None

        # Find the city nearest to last known position
        last_city = self._find_nearest_city(state.last_lat, state.last_lng)
        # Pick a city at least 500 km away
        far_city = self._pick_distant_city(last_city, min_distance_km=500)

        if far_city is None:
            logger.debug(
                "fraud_pattern_skipped",
                pattern="geo_velocity",
                reason="no_distant_city_found",
                user_id=user_id,
            )
            return None

        txn = dict(base_txn)
        txn["latitude"] = CITIES[far_city]["lat"]
        txn["longitude"] = CITIES[far_city]["lng"]
        txn["is_fraud"] = True
        return txn

    # ------------------------------------------------------------------
    # Pattern 4: Unusual Merchant
    # ------------------------------------------------------------------

    def _inject_unusual_merchant(self, user_id: str, base_txn: dict) -> Optional[dict]:
        """
        Forces a grocery/food user to spend ₹50k+ at an electronics merchant.
        Returns None if the user normally buys electronics.
        """
        profile = self.user_registry.get_profile(user_id)

        if "electronics" in profile.usual_merchant_categories:
            logger.debug(
                "fraud_pattern_skipped",
                pattern="unusual_merchant",
                reason="user_already_buys_electronics",
                user_id=user_id,
            )
            return None

        electronics_merchants = self.merchant_registry.by_category("electronics")
        if not electronics_merchants:
            return None

        txn = dict(base_txn)
        txn["merchant_id"] = self.rng.choice(electronics_merchants)
        txn["merchant_category"] = "electronics"
        txn["amount"] = round(
            self.config.UNUSUAL_MERCHANT_MIN_AMOUNT * self.rng.uniform(1.0, 2.0), 2
        )
        txn["is_fraud"] = True
        return txn

    # ------------------------------------------------------------------
    # Pattern 5: Midnight Large
    # ------------------------------------------------------------------

    def _inject_midnight_large(self, base_txn: dict, now_utc: datetime) -> Optional[dict]:
        """
        Forces a large transaction (₹10k+) during IST midnight window (1AM–5AM).
        IST = UTC+5:30 = UTC + 330 minutes.
        """
        ist_offset_minutes = 330
        ist_minutes = (now_utc.hour * 60 + now_utc.minute + ist_offset_minutes) % (24 * 60)
        ist_hour = ist_minutes // 60

        if not (self.config.MIDNIGHT_LARGE_START_HOUR <= ist_hour < self.config.MIDNIGHT_LARGE_END_HOUR):
            logger.debug(
                "fraud_pattern_skipped",
                pattern="midnight_large",
                reason="outside_midnight_window",
                ist_hour=ist_hour,
            )
            return None

        txn = dict(base_txn)
        txn["amount"] = round(
            self.config.MIDNIGHT_LARGE_MIN_AMOUNT * self.rng.uniform(1.0, 3.0), 2
        )
        txn["is_fraud"] = True
        return txn

    # ------------------------------------------------------------------
    # Geo helpers
    # ------------------------------------------------------------------

    def _find_nearest_city(self, lat: float, lng: float) -> str:
        """Return the name of the city whose centre is closest to (lat, lng)."""
        best_city = CITY_NAMES[0]
        best_dist = float("inf")
        for city_name in CITY_NAMES:
            c = CITIES[city_name]
            d = haversine_km(lat, lng, c["lat"], c["lng"])
            if d < best_dist:
                best_dist = d
                best_city = city_name
        return best_city

    def _pick_distant_city(self, from_city: str, min_distance_km: float) -> Optional[str]:
        """Return a random city at least min_distance_km from from_city, or None."""
        from_coords = CITIES[from_city]
        candidates = [
            city for city in CITY_NAMES
            if city != from_city
            and haversine_km(
                from_coords["lat"], from_coords["lng"],
                CITIES[city]["lat"], CITIES[city]["lng"],
            ) >= min_distance_km
        ]
        if not candidates:
            return None
        return self.rng.choice(candidates)
