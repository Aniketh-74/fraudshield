"""
training/features.py — Feature engineering for fraud detection model.

Pure functions with no side effects:
- load_and_validate(csv_path): reads and validates the simulator CSV
- engineer_features(df): computes 14 features (13 user-history + merchant_category_enc)

No MLflow calls, no file I/O except in load_and_validate.
"""
import math
import numpy as np
import pandas as pd
from typing import Tuple
import structlog

from config import MIN_ROWS

log = structlog.get_logger(__name__)

# Exact mapping matching simulator's 6 merchant categories
MERCHANT_CATEGORY_MAP = {
    "groceries": 0,
    "food": 1,
    "electronics": 2,
    "travel": 3,
    "entertainment": 4,
    "transfers": 5,
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Haversine distance in km between two (lat, lng) points.
    Copied verbatim from simulator/fraud_patterns.py — single source of truth.
    """
    R = 6371.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def load_and_validate(csv_path: str) -> pd.DataFrame:
    """
    Load simulator CSV and validate it meets minimum quality requirements.

    Steps:
    1. Read CSV
    2. Parse timestamp as UTC
    3. Deduplicate by transaction_id
    4. Fail fast if row count < MIN_ROWS
    5. Warn if fraud rate outside 2-5%

    Returns validated DataFrame ready for engineer_features().
    """
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.drop_duplicates(subset=["transaction_id"])

    if len(df) < MIN_ROWS:
        raise ValueError(
            f"Dataset has {len(df)} rows, minimum is {MIN_ROWS}. "
            f"Run the simulator longer to generate more transactions."
        )

    fraud_rate = df["is_fraud"].mean()
    if not 0.02 <= fraud_rate <= 0.05:
        log.warning(
            "load_and_validate.fraud_rate_outside_expected_range",
            fraud_rate=float(fraud_rate),
            expected_min=0.02,
            expected_max=0.05,
            note="Proceeding with training — fraud rate warning only",
        )

    log.info(
        "load_and_validate.ok",
        rows=len(df),
        fraud_rate=float(fraud_rate),
        csv_path=csv_path,
    )
    return df


def _compute_user_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-user rolling window features. Uses closed='left' to
    exclude the current transaction from its own window (no lookahead leakage).

    Input df must be sorted by [user_id, timestamp] with timestamp as the index.

    Returns df with 11 new columns added:
      txn_count_1h, txn_count_6h, txn_count_24h,
      avg_amount_7d, amount_deviation, max_amount_24h,
      time_since_last_txn_seconds, unique_merchants_24h, is_new_merchant,
      geo_distance_km, geo_velocity_kmh

    Sentinel values for first transaction per user:
      geo_distance_km = 0.0  (no travel = neutral)
      geo_velocity_kmh = 0.0 (no travel = neutral)
      time_since_last_txn_seconds = -1.0 (no prior transaction)
    """
    df = df.set_index("timestamp")
    results = []

    for user_id, user_df in df.groupby("user_id", sort=False):
        user_df = user_df.sort_index()

        # --- Transaction counts ---
        user_df["txn_count_1h"] = (
            user_df["amount"].rolling("1h", closed="left").count().fillna(0).astype(int)
        )
        user_df["txn_count_6h"] = (
            user_df["amount"].rolling("6h", closed="left").count().fillna(0).astype(int)
        )
        user_df["txn_count_24h"] = (
            user_df["amount"].rolling("24h", closed="left").count().fillna(0).astype(int)
        )

        # --- Amount features ---
        user_df["avg_amount_7d"] = (
            user_df["amount"].rolling("7d", closed="left").mean()
        )
        # Fill NaN avg_amount_7d (first row) with current amount (neutral: deviation=0)
        user_df["avg_amount_7d"] = user_df["avg_amount_7d"].fillna(user_df["amount"])

        stddev_7d = user_df["amount"].rolling("7d", closed="left").std().fillna(0.0)
        user_df["amount_deviation"] = np.where(
            stddev_7d > 0,
            (user_df["amount"] - user_df["avg_amount_7d"]) / stddev_7d,
            0.0,
        )

        user_df["max_amount_24h"] = (
            user_df["amount"].rolling("24h", closed="left").max().fillna(0.0)
        )

        # --- Time since last transaction ---
        # diff() gives NaT for the first row; fill with -1.0
        time_diffs = user_df.index.to_series().diff().dt.total_seconds()
        user_df["time_since_last_txn_seconds"] = time_diffs.fillna(-1.0)

        # --- Unique merchants in 24h (custom rolling unique count) ---
        # rolling().apply(nunique) with raw=False works but is slow;
        # use vectorized approach: for each row, count distinct merchant_id in prior 24h
        timestamps = user_df.index.to_list()
        merchant_ids = user_df["merchant_id"].to_list()
        unique_merchants_24h = []
        for i, ts in enumerate(timestamps):
            cutoff = ts - pd.Timedelta("24h")
            window_merchants = {
                merchant_ids[j] for j in range(i)
                if timestamps[j] > cutoff
            }
            unique_merchants_24h.append(len(window_merchants))
        user_df["unique_merchants_24h"] = unique_merchants_24h

        # --- Is new merchant (O(n) with set) ---
        seen_merchants: set = set()
        is_new = []
        for mid in user_df["merchant_id"]:
            is_new.append(0 if mid in seen_merchants else 1)
            seen_merchants.add(mid)
        user_df["is_new_merchant"] = is_new

        # --- Geo distance and velocity ---
        lats = user_df["latitude"].to_list()
        lngs = user_df["longitude"].to_list()
        time_secs = user_df["time_since_last_txn_seconds"].to_list()
        geo_dist = [0.0]  # sentinel for first transaction
        geo_vel = [0.0]   # sentinel for first transaction
        for i in range(1, len(lats)):
            dist_km = haversine_km(lats[i - 1], lngs[i - 1], lats[i], lngs[i])
            geo_dist.append(dist_km)
            t_hours = time_secs[i] / 3600.0 if time_secs[i] > 0 else 0.0
            vel = (dist_km / t_hours) if t_hours > 0 else 0.0
            geo_vel.append(min(vel, 2000.0))  # cap at 2000 km/h
        user_df["geo_distance_km"] = geo_dist
        user_df["geo_velocity_kmh"] = geo_vel

        results.append(user_df)

    df_out = pd.concat(results)
    return df_out.reset_index()  # restore timestamp as column


def engineer_features(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, list, dict]:
    """
    Transform raw simulator DataFrame into model-ready feature arrays.

    Feature count: 14 total
      - 13 user-history features (FEAT-02): txn_count_*, avg_amount_7d,
        amount_deviation, time_since_last_txn_seconds, unique_merchants_24h,
        max_amount_24h, is_new_merchant, hour_of_day, is_weekend,
        geo_distance_km, geo_velocity_kmh
      - 1 categorical: merchant_category_enc (encoded from raw CSV field)

    Args:
        df: Validated DataFrame from load_and_validate() with timestamp as datetime[UTC]

    Returns:
        X: float64 numpy array, shape (n_samples, 14)
        y: int numpy array, shape (n_samples,)
        feature_names: list of 14 feature name strings in exact column order
        category_mappings: {"merchant_category": MERCHANT_CATEGORY_MAP}
    """
    df = df.copy()
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    # Encode merchant_category to integer
    df["merchant_category_enc"] = (
        df["merchant_category"].map(MERCHANT_CATEGORY_MAP).fillna(-1).astype(int)
    )

    # Compute 11 per-user rolling window features via helper
    df = _compute_user_features(df)

    # Compute IST time features on the full df (no per-user groupby needed)
    ist = df["timestamp"].dt.tz_convert("Asia/Kolkata")
    df["hour_of_day"] = ist.dt.hour
    df["is_weekend"] = ist.dt.dayofweek.isin([5, 6]).astype(int)

    # Exact feature order (14 total) — must match Phase 3 feature_order.json
    FEATURE_COLS = [
        "txn_count_1h",
        "txn_count_6h",
        "txn_count_24h",
        "avg_amount_7d",
        "amount_deviation",
        "time_since_last_txn_seconds",
        "unique_merchants_24h",
        "max_amount_24h",
        "is_new_merchant",
        "hour_of_day",
        "is_weekend",
        "geo_distance_km",
        "geo_velocity_kmh",
        "merchant_category_enc",
    ]

    X = df[FEATURE_COLS].values.astype(np.float64)
    y = df["is_fraud"].values.astype(int)
    category_mappings = {"merchant_category": MERCHANT_CATEGORY_MAP}

    return (X, y, FEATURE_COLS, category_mappings)
