"""
shap_computer.py — SHAP TreeExplainer computation for LightGBM Booster.

Class:
    ShapComputer — loads model.txt + feature_order.json at startup,
                   computes top-5 SHAP values per feature_vector dict

Usage:
    computer = ShapComputer(config.MODEL_TXT_PATH, config.FEATURE_ORDER_PATH)
    top5 = computer.compute(feature_vector_dict)
    # top5: [{"feature": "geo_velocity_kmh", "value": 0.482}, ...]
"""
import json

import numpy as np
import lightgbm as lgb
import shap
import structlog

log = structlog.get_logger(__name__)


class ShapComputer:
    def __init__(self, model_txt_path: str, feature_order_path: str) -> None:
        """
        Load native LightGBM Booster and initialize TreeExplainer.
        Called once at service startup — not per-batch.

        Args:
            model_txt_path:    Path to model.txt (native Booster, saved by training/train.py
                               via booster.save_model()). NOT calibrated_model.pkl.
            feature_order_path: Path to feature_order.json (list of 14 feature name strings,
                               saved by training/train.py via json.dump(feature_names, f)).
        """
        log.info("shap_computer_loading", model=model_txt_path, features=feature_order_path)

        # Load native Booster. If TreeExplainer raises "model type not recognized",
        # add params={"objective": "binary"} to this constructor call.
        self.booster = lgb.Booster(model_file=model_txt_path)

        with open(feature_order_path) as f:
            self.feature_order: list[str] = json.load(f)

        # tree_path_dependent: uses training node counts as background distribution.
        # No external background dataset needed — correct choice for streaming inference.
        self.explainer = shap.TreeExplainer(
            self.booster,
            feature_perturbation="tree_path_dependent",
        )

        log.info(
            "shap_computer_ready",
            n_features=len(self.feature_order),
            feature_names=self.feature_order,
        )

    def compute(self, feature_vector: dict) -> list[dict]:
        """
        Compute top-5 SHAP feature contributions for a single feature_vector.

        Args:
            feature_vector: Dict mapping feature names to float values.
                            Keys that match self.feature_order are used;
                            missing keys default to 0.0.

        Returns:
            List of 5 dicts sorted by abs(value) descending:
            [{"feature": str, "value": float}, ...]
            Values are signed (positive = pushes toward fraud, negative = away from fraud).
            Values rounded to 6 decimal places.
        """
        # Build (1, 14) numpy array in the exact feature order from feature_order.json
        X = np.array(
            [[float(feature_vector.get(f, 0.0)) for f in self.feature_order]],
            dtype=np.float64,
        )

        # Compute SHAP values — handle both return types across SHAP versions
        shap_result = self.explainer.shap_values(X)

        if hasattr(shap_result, "values"):
            # Newer SHAP: Explanation object with .values attribute
            vals: np.ndarray = shap_result.values[0]
        else:
            # SHAP <= 0.46 with native lgb.Booster: returns np.ndarray of shape (1, 14)
            # NOT a list of two arrays (that's for LGBMClassifier / binary sklearn models)
            vals = shap_result[0]

        # Zip feature names with SHAP values, sort by abs descending, take top 5
        named = list(zip(self.feature_order, vals.tolist()))
        named.sort(key=lambda x: abs(x[1]), reverse=True)
        top5 = named[:5]

        return [
            {"feature": name, "value": round(float(val), 6)}
            for name, val in top5
        ]
