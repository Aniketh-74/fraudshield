# ML Training Pipeline

## Purpose

This service trains the fraud detection model used by the Phase 3 ML Scoring Service. It reads the labeled transaction CSV produced by the Phase 1 simulator, engineers 14 features (13 user-history features + merchant category encoding), tunes a LightGBM classifier using Optuna (100 trials, 5-fold stratified cross-validation with SMOTE applied inside each fold), calibrates probabilities with Platt scaling, and exports four artifacts required by Phase 3 before it can run.

## Prerequisites

- Python 3.11+
- The Phase 1 simulator must have run first to produce `data/transactions.csv` (minimum 1,000 transactions)
- pip for local installation, or Docker for containerized runs

## Quick Start (Local)

```bash
cd training/
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set CSV_PATH to the simulator's output CSV
# Example: CSV_PATH=../simulator/data/transactions.csv
python train.py
```

The training job will:
1. Read and validate the CSV
2. Engineer 14 features per transaction
3. Run Optuna hyperparameter optimization (100 trials × 5 folds = 500 LightGBM fits)
4. Train final model with SMOTE on the full training set
5. Calibrate probabilities with Platt scaling
6. Save artifacts to `./artifacts/`
7. Log experiment to `./mlruns/` (or a configured MLflow server)

## Quick Start (Docker)

```bash
# Build the image
docker build -t fraud-training .

# Run training (mount simulator data and output artifacts as volumes)
docker run --rm \
  -v $(pwd)/../simulator/data:/data:ro \
  -v $(pwd)/artifacts:/artifacts \
  -e CSV_PATH=/data/transactions.csv \
  fraud-training
```

With Docker Compose (standalone, before Phase 3):

```bash
N_TRIALS=20 docker compose -f docker-compose.training.yml up --build
```

## Output Artifacts

All four artifacts are required by Phase 3 before the ML Scoring Service can start.

| Artifact | Format | Phase 3 Usage |
|----------|--------|---------------|
| `model.txt` | LightGBM native text | Loaded via `lgb.Booster(model_file=...)` for feature importance / SHAP |
| `calibrated_model.pkl` | joblib pickle | Loaded by ML Scorer for probability inference (`predict_proba`) |
| `feature_order.json` | JSON list of 14 strings | Enforces column order before calling `booster.predict()` |
| `category_mappings.json` | JSON object | Maps `merchant_category` string to int before inference |

**Phase 3 dependency note:** The ML Scorer loads `calibrated_model.pkl` as its primary inference model and uses `feature_order.json` to reorder the 14 input features to match the training-time column order. Column order drift between training and inference causes silent garbage predictions.

## Configuration

All settings are controlled via environment variables. Copy `.env.example` to `.env` and edit as needed.

| Variable | Default | Description |
|----------|---------|-------------|
| `CSV_PATH` | `./data/transactions.csv` | Path to labeled CSV from simulator |
| `MIN_ROWS` | `1000` | Minimum rows required; fail-fast if below |
| `N_TRIALS` | `100` | Number of Optuna hyperparameter trials |
| `TEST_SIZE` | `0.2` | Fraction of data reserved for test set (0.2 = 80/20 split) |
| `CV_FOLDS` | `5` | Number of stratified CV folds inside Optuna objective |
| `RANDOM_SEED` | `42` | Global random seed for reproducibility |
| `MLFLOW_TRACKING_URI` | `file:./mlruns` | MLflow backend URI. Set to `http://localhost:5000` for a server |
| `MLFLOW_EXPERIMENT_NAME` | `fraud-detection-lgbm` | MLflow experiment name |
| `MODEL_OUTPUT_DIR` | `./artifacts` | Output directory for model artifacts |
| `LOG_LEVEL` | `INFO` | Log verbosity (DEBUG, INFO, WARNING, ERROR) |

## Training Time

100 trials × 5 folds = 500 LightGBM fits. Expect 10-30 minutes on a modern laptop, depending on dataset size and `N_TRIALS`. Set `N_TRIALS=10` for a quick smoke test.

## MLflow UI

To view experiment results locally:

```bash
mlflow ui --backend-store-uri ./mlruns
```

Then open http://localhost:5000 in your browser.

Each training run is named by ISO timestamp + dataset hash (e.g., `2026-02-27T13:45:00_abc12345`), enabling easy identification and comparison across runs.

## Logged Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `auc_roc` | Area Under ROC Curve | > 0.95 |
| `recall` | True Positive Rate on test set | > 0.95 |
| `fpr` | False Positive Rate on test set | < 0.05 |
| `ece` | Expected Calibration Error (lower = better calibrated) | - |
| `f1` | F1 Score on test set at 0.5 threshold | - |

If quality gates are not met, a warning is logged and training completes normally (no abort).

## Key Design Decisions

- **SMOTE inside CV folds only:** SMOTE is applied exclusively inside the Optuna cross-validation loop (on each training fold). The test set always uses the original imbalanced distribution (~2-5% fraud) to produce realistic FPR/Recall metrics.
- **Platt calibration on original data:** `CalibratedClassifierCV` is fitted on the original imbalanced training set (not the SMOTE-balanced version), so calibrated probabilities reflect the true ~3% fraud base rate.
- **NopPruner for Optuna:** `MedianPruner` is incompatible with 5-fold CV (Optuna GitHub issue #3203). `NopPruner` is used instead.
- **14 features:** 13 user-history features (FEAT-02) + `merchant_category_enc` (strong fraud signal from raw CSV field).
