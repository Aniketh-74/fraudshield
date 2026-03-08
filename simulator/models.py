"""
models.py — Transaction dataclass, UserProfile, UserState, MerchantRegistry, UserRegistry.

The Transaction dataclass is the canonical model: both Kafka serialization and CSV
writing derive from the same object to prevent field name drift.
"""
import random
from collections import deque
from dataclasses import dataclass, asdict, field
from typing import Optional

from cities import CITY_NAMES


# ---------------------------------------------------------------------------
# Transaction — canonical 12-field model + is_fraud ground truth
# ---------------------------------------------------------------------------

@dataclass
class Transaction:
    transaction_id: str      # uuid4 hex string
    user_id: str             # "user_0001" format
    merchant_id: str         # "merchant_001" format
    amount: float            # INR, 2 decimal places
    currency: str            # Always "INR"
    merchant_category: str   # One of 6 categories
    latitude: float          # City centre lat
    longitude: float         # City centre lng
    timestamp: str           # ISO 8601 UTC string
    device_id: str           # uuid4 hex string
    is_international: bool   # Always False for simulator v1
    is_fraud: bool           # Ground truth — written to CSV only, NOT Kafka

    def to_kafka_dict(self) -> dict:
        """Returns dict WITHOUT is_fraud for Kafka publication."""
        d = asdict(self)
        d.pop("is_fraud")
        return d

    def to_csv_dict(self) -> dict:
        """Returns dict WITH is_fraud as int (1/0) for CSV."""
        d = asdict(self)
        d["is_fraud"] = 1 if self.is_fraud else 0
        return d


# ---------------------------------------------------------------------------
# UserProfile — static spending profile assigned at startup
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    user_id: str
    avg_spend: float                        # INR, range [500, 50000]
    std_dev: float                          # 10–30% of avg_spend
    home_city: str                          # From CITY_NAMES
    usual_merchant_categories: list         # 2–3 categories from the 6


# ---------------------------------------------------------------------------
# UserState — mutable per-user state updated after every transaction
# ---------------------------------------------------------------------------

@dataclass
class UserState:
    recent_timestamps: deque = field(default_factory=lambda: deque(maxlen=10))
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None
    last_ts: Optional[float] = None
    fraud_cooldown_until: float = 0.0


# ---------------------------------------------------------------------------
# MerchantRegistry — deterministic category assignment for 200 merchants
# ---------------------------------------------------------------------------

# Fixed partition table from CONTEXT.md / RESEARCH.md:
#   merchant_001–080  -> groceries  (80)
#   merchant_081–130  -> food       (50)
#   merchant_131–155  -> electronics (25)
#   merchant_156–175  -> travel     (20)
#   merchant_176–190  -> entertainment (15)
#   merchant_191–200  -> transfers  (10)

_MERCHANT_RANGES = [
    (1,   80,  "groceries"),
    (81,  130, "food"),
    (131, 155, "electronics"),
    (156, 175, "travel"),
    (176, 190, "entertainment"),
    (191, 200, "transfers"),
]


class MerchantRegistry:
    def __init__(self) -> None:
        self._category_map: dict[str, str] = {}
        self._by_category: dict[str, list[str]] = {}

        for start, end, category in _MERCHANT_RANGES:
            self._by_category[category] = []
            for i in range(start, end + 1):
                merchant_id = f"merchant_{i:03d}"
                self._category_map[merchant_id] = category
                self._by_category[category].append(merchant_id)

    def get_category(self, merchant_id: str) -> str:
        """Return the category for a given merchant_id."""
        return self._category_map[merchant_id]

    def by_category(self, category: str) -> list:
        """Return list of merchant_ids for the given category."""
        return self._by_category.get(category, [])

    def random_merchant(self, rng: random.Random) -> str:
        """Return a random merchant_id from any category."""
        all_merchants = list(self._category_map.keys())
        return rng.choice(all_merchants)

    def random_merchant_for_category(self, category: str, rng: random.Random) -> str:
        """Return a random merchant_id from the specified category."""
        merchants = self._by_category[category]
        return rng.choice(merchants)


# ---------------------------------------------------------------------------
# UserRegistry — generates NUM_USERS profiles and states at construction
# ---------------------------------------------------------------------------

_ALL_CATEGORIES = ["groceries", "food", "electronics", "travel", "entertainment", "transfers"]


class UserRegistry:
    def __init__(self, config, rng: random.Random) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self._states: dict[str, UserState] = {}
        self._user_ids: list[str] = []

        for i in range(1, config.NUM_USERS + 1):
            user_id = f"user_{i:04d}"
            self._user_ids.append(user_id)

            avg_spend = rng.uniform(500, 50000)
            std_dev = avg_spend * rng.uniform(0.1, 0.3)
            home_city = rng.choice(CITY_NAMES)
            num_categories = rng.randint(2, 3)
            usual_categories = rng.sample(_ALL_CATEGORIES, num_categories)

            self._profiles[user_id] = UserProfile(
                user_id=user_id,
                avg_spend=avg_spend,
                std_dev=std_dev,
                home_city=home_city,
                usual_merchant_categories=usual_categories,
            )
            self._states[user_id] = UserState()

    def get_profile(self, user_id: str) -> UserProfile:
        return self._profiles[user_id]

    def get_state(self, user_id: str) -> UserState:
        return self._states[user_id]

    def random_user_id(self, rng: random.Random) -> str:
        return rng.choice(self._user_ids)

    def update_state(self, user_id: str, lat: float, lng: float, ts: float) -> None:
        state = self._states[user_id]
        state.recent_timestamps.append(ts)
        state.last_lat = lat
        state.last_lng = lng
        state.last_ts = ts
