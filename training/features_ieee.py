"""
training/features_ieee.py — Feature engineering for the IEEE-CIS Fraud Detection dataset.

Two public functions:
    load_and_validate(txn_path, idn_path) -> pd.DataFrame
    engineer_features(df)                -> (X, y, feature_names, category_mappings)

Feature set (32 total):
    Temporal     : hour_of_day, day_of_week, is_weekend
    Amount       : TransactionAmt, amt_log, amt_to_card1_mean_ratio
    Card         : card1, card2_enc, card4_enc, card6_enc
    Address      : addr1_enc
    Email        : P_emaildomain_enc
    Distance     : dist1_filled
    C-features   : C1, C2, C5, C6, C13, C14
    D-features   : D1_filled, D2_filled, D15_filled
    M-flags      : M4_enc, M6_enc
    V-features   : V12, V37, V58, V94, V130, V307, V308, V317

UID strategy:
    uid = str(card1) + '_' + str(int(addr1)) — proxy for a recurring customer.
    Used to compute per-uid aggregated features (amt ratio).

Real-time inference mapping:
    Most features are static per-transaction (card fields, email, C/D/V values).
    amt_to_card1_mean_ratio requires a running mean per card1 — tracked in Redis.
"""
import math
import numpy as np
import pandas as pd
from typing import Tuple
import structlog

from config import MIN_ROWS

log = structlog.get_logger(__name__)

# ── Categorical encodings ──────────────────────────────────────────────────────

CARD4_MAP = {"visa": 0, "mastercard": 1, "american express": 2, "discover": 3}
CARD6_MAP = {"debit": 0, "credit": 1, "debit or credit": 2, "charge card": 3}
M4_MAP    = {"M0": 0, "M1": 1, "M2": 2}
M6_MAP    = {"F": 0, "T": 1}

# ProductCD is not used here (not available in real-time without enrichment)
# addr1 and P_emaildomain are label-encoded at engineer time; mappings are saved.


# ── Selected V-features ───────────────────────────────────────────────────────
# Chosen by: (1) 0% or 13% NaN rate groups, (2) high variance, (3) known
# importance from published Kaggle solutions.  Only 8 kept to stay interpretable.
V_FEATURES = ["V12", "V37", "V58", "V94", "V130", "V307", "V308", "V317"]


def load_and_validate(txn_path: str, idn_path: str) -> pd.DataFrame:
    """
    Load and merge train_transaction.csv + train_identity.csv.

    Steps:
    1. Read both CSVs with memory-efficient dtypes
    2. Left-merge on TransactionID (identity covers ~24% of rows)
    3. Deduplicate by TransactionID
    4. Validate minimum rows and fraud rate
    5. Return merged DataFrame
    """
    log.info("ieee.load_start", txn_path=txn_path, idn_path=idn_path)

    # dtype downcasting for memory efficiency (~8GB → ~3GB)
    txn_dtypes = {
        "TransactionID": "int32", "isFraud": "int8", "TransactionDT": "int32",
        "TransactionAmt": "float32",
        "card1": "int16", "card2": "float32", "card3": "float32",
        "card5": "float32",
        "addr1": "float32", "addr2": "float32",
        "dist1": "float32", "dist2": "float32",
        **{f"C{i}": "float32" for i in range(1, 15)},
        **{f"D{i}": "float32" for i in range(1, 16)},
        **{f"V{i}": "float32" for i in range(1, 340)},
    }
    idn_dtypes = {
        "TransactionID": "int32",
        **{f"id_{str(i).zfill(2)}": "float32" for i in range(1, 12)},
    }

    txn = pd.read_csv(txn_path, dtype={k: v for k, v in txn_dtypes.items()})
    with open(idn_path) as _f:
        idn_header = _f.readline()
    idn = pd.read_csv(idn_path, dtype={k: v for k, v in idn_dtypes.items() if k in idn_header})
    df  = txn.merge(idn[["TransactionID", "id_01", "id_02"]], on="TransactionID", how="left")
    df  = df.drop_duplicates(subset=["TransactionID"])

    if len(df) < MIN_ROWS:
        raise ValueError(
            f"Dataset has {len(df)} rows, minimum is {MIN_ROWS}."
        )

    fraud_rate = float(df["isFraud"].mean())
    if not 0.02 <= fraud_rate <= 0.06:
        log.warning(
            "ieee.fraud_rate_outside_expected_range",
            fraud_rate=fraud_rate,
            note="Proceeding — IEEE-CIS has ~3.5% fraud rate",
        )

    log.info("ieee.load_ok", rows=len(df), fraud_rate=fraud_rate)
    return df


def _label_encode(series: pd.Series, mapping: dict | None = None) -> Tuple[pd.Series, dict]:
    """
    Label-encode a string/object series. Returns (encoded_series, mapping_dict).
    NaN → -1. Unknown categories get -1 at inference time.

    If mapping is provided, uses it (for consistent inference encoding).
    Otherwise builds mapping from series values.
    """
    if mapping is None:
        unique_vals = sorted(series.dropna().unique())
        mapping = {str(v): i for i, v in enumerate(unique_vals)}
    encoded = series.map(lambda x: mapping.get(str(x), -1) if pd.notna(x) else -1).astype("int16")
    return encoded, mapping


def engineer_features(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, list, dict]:
    """
    Transform merged IEEE-CIS DataFrame into model-ready arrays.

    Feature count: 32 total
    Returns:
        X              : float32 numpy array, shape (n_samples, 30)
        y              : int8 numpy array, shape (n_samples,)
        feature_names  : list of 30 feature name strings
        category_mappings: dict of all label-encoding mappings (for inference)
    """
    df = df.copy()

    category_mappings: dict = {}

    # ── 1. Temporal features ─────────────────────────────────────────────────
    # TransactionDT is seconds from a hidden reference date.
    # hour_of_day and day_of_week are still meaningful (periodicity preserved).
    dt = df["TransactionDT"].astype("int64")
    df["hour_of_day"] = ((dt // 3600) % 24).astype("int8")
    df["day_of_week"]  = ((dt // 86400) % 7).astype("int8")
    df["is_weekend"]   = df["day_of_week"].isin([5, 6]).astype("int8")

    # ── 2. Amount features ────────────────────────────────────────────────────
    df["amt_log"] = np.log1p(df["TransactionAmt"].astype("float64")).astype("float32")

    # Per-card1 mean amount ratio — captures "is this amount unusual for this card?"
    card1_mean = df.groupby("card1")["TransactionAmt"].transform("mean")
    df["amt_to_card1_mean_ratio"] = (
        df["TransactionAmt"].astype("float64") / (card1_mean.astype("float64") + 1e-9)
    ).astype("float32")

    # ── 3. Card features ──────────────────────────────────────────────────────
    # card1: numerical card identifier — high cardinality but highly predictive
    # card2: partial card number — treat as float, fill NaN with median
    df["card2_filled"] = df["card2"].fillna(df["card2"].median()).astype("float32")

    df["card4_enc"], card4_mapping = _label_encode(df["card4"], CARD4_MAP)
    df["card6_enc"], card6_mapping = _label_encode(df["card6"], CARD6_MAP)
    category_mappings["card4"] = card4_mapping
    category_mappings["card6"] = card6_mapping

    # ── 4. Address ────────────────────────────────────────────────────────────
    df["addr1_enc"], addr1_mapping = _label_encode(
        df["addr1"].fillna(-1).astype(int).astype(str)
    )
    category_mappings["addr1"] = addr1_mapping

    # ── 5. Email domain ───────────────────────────────────────────────────────
    # Normalize: keep domain, map unknown → "other"
    df["p_email_clean"] = df["P_emaildomain"].fillna("unknown").str.lower().str.strip()
    df["p_email_enc"], p_email_mapping = _label_encode(df["p_email_clean"])
    category_mappings["P_emaildomain"] = p_email_mapping

    # ── 6. Distance ───────────────────────────────────────────────────────────
    # dist1 has 60% NaN — fill with 0 (no distance info = local transaction)
    df["dist1_filled"] = df["dist1"].fillna(0.0).astype("float32")

    # ── 7. C-features (counting features) ────────────────────────────────────
    # C1: how many addresses with this card; C2: similar but different grouping
    # C5/C6: purchase count variants; C13/C14: card/address match counts
    # Already float32, fill rare NaN with 0
    for c in ["C1", "C2", "C5", "C6", "C13", "C14"]:
        df[c] = df[c].fillna(0.0).astype("float32")

    # ── 8. D-features (time delta features) ──────────────────────────────────
    # D1: days since card was opened (0.2% NaN → fill with median)
    # D2: days since last transaction (47% NaN → fill with -1 sentinel)
    # D15: days since last addr change (15% NaN → fill with -1 sentinel)
    df["D1_filled"]  = df["D1"].fillna(df["D1"].median()).astype("float32")
    df["D2_filled"]  = df["D2"].fillna(-1.0).astype("float32")
    df["D15_filled"] = df["D15"].fillna(-1.0).astype("float32")

    # ── 9. M-flags (match flags) ──────────────────────────────────────────────
    df["M4_enc"], m4_mapping = _label_encode(df["M4"], M4_MAP)
    df["M6_enc"], m6_mapping = _label_encode(df["M6"], M6_MAP)
    category_mappings["M4"] = m4_mapping
    category_mappings["M6"] = m6_mapping

    # ── 10. V-features ────────────────────────────────────────────────────────
    # 8 selected V-features from 0%/13% NaN groups with high variance/importance.
    # Fill NaN with median (per-column).
    for v in V_FEATURES:
        df[v] = df[v].fillna(df[v].median()).astype("float32")

    # ── Assemble feature matrix ───────────────────────────────────────────────
    FEATURE_COLS = [
        # Temporal
        "hour_of_day",
        "day_of_week",
        "is_weekend",
        # Amount
        "TransactionAmt",
        "amt_log",
        "amt_to_card1_mean_ratio",
        # Card
        "card1",
        "card2_filled",
        "card4_enc",
        "card6_enc",
        # Address / email / distance
        "addr1_enc",
        "p_email_enc",
        "dist1_filled",
        # C-features
        "C1", "C2", "C5", "C6", "C13", "C14",
        # D-features
        "D1_filled", "D2_filled", "D15_filled",
        # M-flags
        "M4_enc", "M6_enc",
        # V-features
        *V_FEATURES,
    ]

    X = df[FEATURE_COLS].values.astype(np.float32)
    y = df["isFraud"].values.astype(np.int8)

    log.info(
        "ieee.features_engineered",
        rows=X.shape[0],
        features=X.shape[1],
        fraud_rate=float(y.mean()),
    )

    return X, y, FEATURE_COLS, category_mappings
