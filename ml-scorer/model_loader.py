"""
model_loader.py — Load calibrated_model.pkl and feature_order.json from MODEL_DIR.

Functions:
    load_model_artifacts(model_dir: str) -> dict

Returns dict with keys:
    "calibrated_model"  — CalibratedClassifierCV object (sklearn)
    "feature_order"     — list of 14 feature name strings
    "model_version"     — str, from model_version.txt or derived from pkl mtime

Raises:
    FileNotFoundError: if calibrated_model.pkl or feature_order.json is missing
    RuntimeError: if feature_order.json contains != 14 features
"""
import json
import os
from pathlib import Path

import joblib
import structlog

log = structlog.get_logger(__name__)

_EXPECTED_FEATURE_COUNT = 14


def load_model_artifacts(model_dir: str) -> dict:
    """
    Load all model artifacts from model_dir.

    Files read:
        {model_dir}/calibrated_model.pkl  — joblib.load() → CalibratedClassifierCV
        {model_dir}/feature_order.json    — json.load() → list of 14 strings
        {model_dir}/model_version.txt     — strip() → str; fallback: pkl file mtime

    Returns:
        {
            "calibrated_model": <CalibratedClassifierCV>,
            "feature_order": ["txn_count_1h", ..., "merchant_category_enc"],
            "model_version": "v1" or timestamp-based string
        }
    """
    model_dir_path = Path(model_dir)

    pkl_path = model_dir_path / "calibrated_model.pkl"
    feature_order_path = model_dir_path / "feature_order.json"
    version_path = model_dir_path / "model_version.txt"

    # Validate required files exist before attempting load
    if not pkl_path.exists():
        raise FileNotFoundError(
            f"calibrated_model.pkl not found at {pkl_path}. "
            f"Run training pipeline first or check MODEL_DIR={model_dir}"
        )
    if not feature_order_path.exists():
        raise FileNotFoundError(
            f"feature_order.json not found at {feature_order_path}. "
            f"Run training pipeline first or check MODEL_DIR={model_dir}"
        )

    log.info("model_loading", pkl_path=str(pkl_path))
    calibrated_model = joblib.load(str(pkl_path))
    log.info("model_loaded", pkl_path=str(pkl_path))

    with open(feature_order_path, "r") as f:
        feature_order: list = json.load(f)

    if len(feature_order) != _EXPECTED_FEATURE_COUNT:
        raise RuntimeError(
            f"feature_order.json contains {len(feature_order)} features, "
            f"expected {_EXPECTED_FEATURE_COUNT}. "
            f"Ensure the training pipeline produced the correct feature_order.json."
        )

    # Derive model version
    if version_path.exists():
        model_version = version_path.read_text().strip()
    else:
        # Fallback: use mtime of pkl file as version identifier
        mtime = os.path.getmtime(str(pkl_path))
        from datetime import datetime
        model_version = datetime.utcfromtimestamp(mtime).strftime("v%Y%m%d")

    log.info(
        "model_artifacts_loaded",
        model_version=model_version,
        feature_count=len(feature_order),
        feature_order=feature_order,
    )

    return {
        "calibrated_model": calibrated_model,
        "feature_order": feature_order,
        "model_version": model_version,
    }
