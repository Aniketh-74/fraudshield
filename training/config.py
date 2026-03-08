import os

# Data ingestion
CSV_PATH = os.environ.get("CSV_PATH", "./data/transactions.csv")
MIN_ROWS = int(os.environ.get("MIN_ROWS", "1000"))

# Training
N_TRIALS = int(os.environ.get("N_TRIALS", "100"))
TEST_SIZE = float(os.environ.get("TEST_SIZE", "0.2"))
CV_FOLDS = int(os.environ.get("CV_FOLDS", "5"))
RANDOM_SEED = int(os.environ.get("RANDOM_SEED", "42"))

# MLflow
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "file:./mlruns")
MLFLOW_EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "fraud-detection-lgbm")

# Output
MODEL_OUTPUT_DIR = os.environ.get("MODEL_OUTPUT_DIR", "./artifacts")

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
