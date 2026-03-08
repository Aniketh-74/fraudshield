"""
training/train.py — Main entrypoint for the fraud detection ML training pipeline.

Orchestrates:
1. Data loading and validation (from features.py or features_ieee.py)
2. Feature engineering
3. Train/test split
4. Optuna hyperparameter optimization (100 trials, 5-fold CV, SMOTE inside each fold)
5. Final model training with SMOTE on full training set
6. Platt calibration on original (non-SMOTE) training data
7. MLflow experiment logging (params, metrics, artifacts, figures)
8. Artifact export (model.txt, calibrated_model.pkl, feature_order.json, category_mappings.json)

Usage:
    python train.py                          # simulator CSV (default)
    python train.py --dataset ieee-cis       # IEEE-CIS Fraud Detection dataset

Environment variables: see config.py and .env.example
"""
import argparse
import os
import sys
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import joblib
import lightgbm as lgb
import mlflow
import optuna
import structlog
import matplotlib.pyplot as plt
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    roc_auc_score,
    recall_score,
    precision_recall_curve,
    ConfusionMatrixDisplay,
    f1_score,
)
from sklearn.model_selection import train_test_split, StratifiedKFold
from imblearn.over_sampling import SMOTE

from config import (
    CSV_PATH,
    N_TRIALS,
    TEST_SIZE,
    CV_FOLDS,
    RANDOM_SEED,
    MLFLOW_TRACKING_URI,
    MLFLOW_EXPERIMENT_NAME,
    MODEL_OUTPUT_DIR,
    LOG_LEVEL,
)

# ---------------------------------------------------------------------------
# Structured logging setup (JSON for Docker, consistent with project-wide standard)
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def compute_file_hash(filepath: str, chunk_size: int = 8192) -> str:
    """
    SHA256 hash of file contents, read in chunks (memory-safe for large CSVs).
    Returns first 8 hex chars (sufficient for run naming uniqueness).
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()[:8]


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """
    Expected Calibration Error (ECE).
    ECE = sum_over_bins( |bin_size / n_total| * |avg_confidence - fraction_positives| )

    Uses calibration_curve for binning, then weights by bin population.
    Lower is better; 0.0 = perfect calibration.

    Source: Guo et al. 2017, "On Calibration of Modern Neural Networks"
    """
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins)
    # Reconstruct bin counts from y_prob to compute proper weighted ECE
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)
    bin_counts = np.bincount(bin_indices, minlength=n_bins)
    # Only bins with samples (calibration_curve skips empty bins)
    nonempty_bins = bin_counts > 0
    n_total = len(y_true)
    ece = np.sum(
        (bin_counts[nonempty_bins] / n_total)
        * np.abs(prob_true - prob_pred)
    )
    return float(ece)


# ---------------------------------------------------------------------------
# Cross-validation with SMOTE inside each fold
# ---------------------------------------------------------------------------

def cv_auc(
    X_train_full: np.ndarray,
    y_train_full: np.ndarray,
    params: dict,
    n_splits: int,
    seed: int,
) -> float:
    """
    Run n_splits-fold stratified CV with SMOTE applied INSIDE each fold.

    CRITICAL rules:
    - SMOTE is applied ONLY to X_fold_train, y_fold_train (never X_train_full)
    - eval_set uses X_fold_val, y_fold_val (NEVER X_test, y_test — those must not enter Optuna)
    - Uses NopPruner — step-based pruning is incompatible with k-fold CV (optuna issue #3203)

    Returns mean AUC-ROC across all folds.
    """
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    fold_aucs = []

    for fold_train_idx, fold_val_idx in skf.split(X_train_full, y_train_full):
        X_fold_train = X_train_full[fold_train_idx]
        y_fold_train = y_train_full[fold_train_idx]
        X_fold_val = X_train_full[fold_val_idx]
        y_fold_val = y_train_full[fold_val_idx]

        # Apply SMOTE ONLY to this training fold
        smote = SMOTE(random_state=seed)
        X_resampled, y_resampled = smote.fit_resample(X_fold_train, y_fold_train)

        clf = lgb.LGBMClassifier(**params)
        clf.fit(
            X_resampled,
            y_resampled,
            eval_set=[(X_fold_val, y_fold_val)],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
        )

        val_proba = clf.predict_proba(X_fold_val)[:, 1]
        fold_aucs.append(roc_auc_score(y_fold_val, val_proba))

    return float(np.mean(fold_aucs))


# ---------------------------------------------------------------------------
# Optuna objective factory
# ---------------------------------------------------------------------------

def make_objective(X_train: np.ndarray, y_train: np.ndarray):
    """
    Returns an Optuna objective function that tunes 8 LightGBM hyperparameters
    by maximizing 5-fold CV AUC-ROC with SMOTE inside each fold.
    """
    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "binary",
            "metric": "auc",
            "num_leaves": trial.suggest_int("num_leaves", 20, 300),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 200),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 1.0),
            "n_estimators": 1000,
            "scale_pos_weight": (y_train == 0).sum() / (y_train == 1).sum(),
            "verbose": -1,
            "random_state": RANDOM_SEED,
        }
        return cv_auc(X_train, y_train, params, n_splits=CV_FOLDS, seed=RANDOM_SEED)

    return objective


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Full training pipeline:
    1. Load + validate CSV (simulator or IEEE-CIS depending on --dataset)
    2. Engineer features
    3. Train/test split (stratified 80/20)
    4. Optuna study (100 trials, 5-fold CV, SMOTE per fold)
    5. Final model training (SMOTE on full training set)
    6. Platt calibration (on original imbalanced training data)
    7. Evaluation on test set
    8. MLflow logging (params, metrics, artifacts, figures)
    9. Artifact export (model.txt, calibrated_model.pkl, feature_order.json, category_mappings.json)
    """
    parser = argparse.ArgumentParser(description="Fraud detection model training")
    parser.add_argument(
        "--dataset",
        choices=["simulator", "ieee-cis"],
        default="simulator",
        help="Dataset to train on: 'simulator' (default) or 'ieee-cis'",
    )
    args = parser.parse_args()

    # Setup output directory
    output_dir = Path(MODEL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("training.start", dataset=args.dataset, n_trials=N_TRIALS, cv_folds=CV_FOLDS)

    # 1. Load and validate dataset
    if args.dataset == "ieee-cis":
        from features_ieee import load_and_validate as load_ieee, engineer_features as eng_ieee
        txn_path = os.environ.get("IEEE_TXN_PATH", "./data/train_transaction.csv")
        idn_path = os.environ.get("IEEE_IDN_PATH", "./data/train_identity.csv")
        df = load_ieee(txn_path, idn_path)
        log.info("training.data_loaded", rows=len(df), dataset="ieee-cis")
        X, y, feature_names, category_mappings = eng_ieee(df)
        dataset_hash = txn_path  # use path as hash seed for ieee (too large for full hash)
    else:
        from features import load_and_validate, engineer_features
        df = load_and_validate(CSV_PATH)
        log.info("training.data_loaded", rows=len(df))
        X, y, feature_names, category_mappings = engineer_features(df)
        dataset_hash = compute_file_hash(CSV_PATH)
    fraud_rate = float(y.mean())
    log.info(
        "training.features_engineered",
        rows=X.shape[0],
        features=X.shape[1],
        fraud_rate=fraud_rate,
        feature_names=feature_names,
    )

    # 3. Train/test split (stratified to preserve fraud rate in both splits)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )
    log.info(
        "training.split",
        train_size=X_train.shape[0],
        test_size=X_test.shape[0],
        train_fraud_rate=float(y_train.mean()),
        test_fraud_rate=float(y_test.mean()),
    )

    # Guard: ensure test set uses original imbalanced distribution (not resampled)
    assert 0.005 <= y_test.mean() <= 0.10, (
        f"Test set fraud rate {y_test.mean():.3f} is outside expected range [0.005, 0.10]. "
        "Check that SMOTE was not applied before train_test_split."
    )

    # 4. Run naming
    run_name = f"{args.dataset}_{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}"
    log.info("training.run_name", run_name=run_name)

    # 5. Configure MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    # 6. Optuna hyperparameter study
    log.info("training.optuna_start", n_trials=N_TRIALS)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=RANDOM_SEED),
        pruner=optuna.pruners.NopPruner(),  # Step-based pruners incompatible with k-fold CV (optuna issue #3203)
        storage=f"sqlite:///{output_dir}/optuna_study.db",  # resume on crash
        study_name=f"fraud-lgbm-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        load_if_exists=True,
    )
    study.optimize(
        make_objective(X_train, y_train),
        n_trials=N_TRIALS,
        show_progress_bar=True,
    )
    log.info(
        "training.optuna_complete",
        best_auc=study.best_value,
        best_params=study.best_params,
    )

    # 7. Final model training on full training set (with SMOTE)
    final_params = {
        "objective": "binary",
        "metric": "auc",
        "n_estimators": 1000,
        "scale_pos_weight": (y_train == 0).sum() / (y_train == 1).sum(),
        "verbose": -1,
        "random_state": RANDOM_SEED,
        **study.best_params,
    }

    # Apply SMOTE to full training set for final model
    smote_final = SMOTE(random_state=RANDOM_SEED)
    X_train_res, y_train_res = smote_final.fit_resample(X_train, y_train)
    log.info(
        "training.smote_applied",
        original_train_size=X_train.shape[0],
        resampled_train_size=X_train_res.shape[0],
    )

    best_clf = lgb.LGBMClassifier(**final_params)
    best_clf.fit(
        X_train_res,
        y_train_res,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )
    log.info(
        "training.final_model_trained",
        best_iteration=best_clf.best_iteration_,
    )

    # Extract native booster and save model.txt
    booster = best_clf.booster_
    model_txt_path = str(output_dir / "model.txt")
    booster.save_model(model_txt_path)
    log.info("training.model_txt_saved", path=model_txt_path)

    # 8. Platt calibration on ORIGINAL (non-SMOTE) training data
    # CRITICAL: CalibratedClassifierCV must see the real ~3% fraud rate distribution
    # Calibrating on SMOTE-balanced data produces wrong probability estimates
    calibration_params = {**final_params, "n_estimators": best_clf.best_iteration_}
    base_for_calibration = lgb.LGBMClassifier(**calibration_params)
    calibrated_clf = CalibratedClassifierCV(
        base_for_calibration,
        method="sigmoid",  # Platt scaling — locked in CONTEXT.md
        cv=5,
    )
    calibrated_clf.fit(X_train, y_train)  # RAW imbalanced data — calibrator must see real distribution
    log.info("training.calibration_complete", method="sigmoid", cv=5)

    # 9. Save all artifacts
    calibrated_pkl_path = str(output_dir / "calibrated_model.pkl")
    joblib.dump(calibrated_clf, calibrated_pkl_path)
    log.info("training.calibrated_model_saved", path=calibrated_pkl_path)

    feature_order_path = str(output_dir / "feature_order.json")
    with open(feature_order_path, "w") as f:
        json.dump(feature_names, f, indent=2)
    log.info("training.feature_order_saved", path=feature_order_path, n_features=len(feature_names))

    category_mappings_path = str(output_dir / "category_mappings.json")
    with open(category_mappings_path, "w") as f:
        json.dump(category_mappings, f, indent=2)
    log.info("training.category_mappings_saved", path=category_mappings_path)

    # 10. Evaluate on test set (NEVER use resampled data here)
    # Guard: verify test set is not resampled (fraud rate should be ~2-5%)
    assert 0.005 <= y_test.mean() <= 0.10, (
        f"Test set fraud rate {y_test.mean():.3f} suggests test set was resampled. "
        "Test evaluation must use original imbalanced distribution."
    )

    y_pred_proba = calibrated_clf.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    auc = roc_auc_score(y_test, y_pred_proba)
    recall = recall_score(y_test, y_pred)
    fp = ((y_pred == 1) & (y_test == 0)).sum()
    tn = ((y_pred == 0) & (y_test == 0)).sum()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    ece = compute_ece(y_test, y_pred_proba)
    f1 = f1_score(y_test, y_pred)

    # PR-AUC and Recall@95% precision
    precision_vals, recall_vals, pr_thresholds = precision_recall_curve(y_test, y_pred_proba)
    pr_auc = float(np.trapezoid(precision_vals[::-1], recall_vals[::-1]))
    # Find highest recall where precision >= 0.95
    high_prec_mask = precision_vals >= 0.95
    recall_at_95_prec = float(recall_vals[high_prec_mask].max()) if high_prec_mask.any() else 0.0

    log.info(
        "training.metrics",
        auc_roc=auc,
        recall=recall,
        fpr=fpr,
        ece=ece,
        f1=f1,
        pr_auc=pr_auc,
        recall_at_95_prec=recall_at_95_prec,
    )

    # Quality gate warnings (do not abort training — log only)
    if auc < 0.95:
        log.warning("training.quality_gate_failed", metric="auc_roc", value=auc, threshold=0.95)
    if recall < 0.95:
        log.warning("training.quality_gate_failed", metric="recall", value=recall, threshold=0.95)
    if fpr >= 0.05:
        log.warning("training.quality_gate_failed", metric="fpr", value=fpr, threshold=0.05)

    # 11. MLflow logging
    with mlflow.start_run(run_name=run_name):
        # Log hyperparameters
        mlflow.log_params(study.best_params)
        mlflow.log_params({
            "n_rows": len(df),
            "fraud_rate": float(y.mean()),
            "n_features": len(feature_names),
            "n_trials": N_TRIALS,
            "dataset": args.dataset,
        })

        # Log metrics
        mlflow.log_metrics({
            "auc_roc": auc,
            "recall": recall,
            "fpr": fpr,
            "ece": ece,
            "f1": f1,
            "pr_auc": pr_auc,
            "recall_at_95_prec": recall_at_95_prec,
        })

        # Log model artifacts
        mlflow.log_artifact(model_txt_path)
        mlflow.log_artifact(calibrated_pkl_path)
        mlflow.log_artifact(feature_order_path)
        mlflow.log_artifact(category_mappings_path)

        # Log confusion matrix PNG
        fig, ax = plt.subplots(figsize=(6, 5))
        ConfusionMatrixDisplay.from_predictions(y_test, y_pred, ax=ax)
        ax.set_title("Confusion Matrix (Test Set)")
        mlflow.log_figure(fig, "confusion_matrix.png")
        plt.close(fig)

        # Log calibration curve PNG
        prob_true, prob_pred = calibration_curve(y_test, y_pred_proba, n_bins=10)
        fig2, ax2 = plt.subplots(figsize=(6, 5))
        ax2.plot(prob_pred, prob_true, marker="o", label="Calibration curve")
        ax2.plot([0, 1], [0, 1], linestyle="--", label="Perfect calibration")
        ax2.set_xlabel("Mean predicted probability")
        ax2.set_ylabel("Fraction of positives")
        ax2.set_title("Calibration Curve (Platt Scaling)")
        ax2.legend()
        mlflow.log_figure(fig2, "calibration_curve.png")
        plt.close(fig2)

        # Log feature importance PNG
        fig3, ax3 = plt.subplots(figsize=(8, 6))
        lgb.plot_importance(booster, max_num_features=len(feature_names), ax=ax3, title="Feature Importance")
        mlflow.log_figure(fig3, "feature_importance.png")
        plt.close(fig3)

    log.info(
        "training.complete",
        auc_roc=auc,
        recall=recall,
        fpr=fpr,
        ece=ece,
        output_dir=str(output_dir),
        run_name=run_name,
    )

    # Final summary
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"  AUC-ROC:  {auc:.4f}  (gate: > 0.95)")
    print(f"  Recall:   {recall:.4f}  (gate: > 0.95)")
    print(f"  FPR:      {fpr:.4f}  (gate: < 0.05)")
    print(f"  ECE:      {ece:.4f}  (lower = better calibration)")
    print(f"  F1:       {f1:.4f}")
    print(f"\nArtifacts saved to: {output_dir}")
    print(f"  - model.txt")
    print(f"  - calibrated_model.pkl")
    print(f"  - feature_order.json  ({len(feature_names)} features)")
    print(f"  - category_mappings.json")
    print(f"\nMLflow experiment: {MLFLOW_EXPERIMENT_NAME}")
    print(f"  Run: {run_name}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
