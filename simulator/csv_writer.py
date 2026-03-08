"""
csv_writer.py — CSVWriter class with 100-transaction buffer and SIGTERM-safe flush.

Design notes:
  - Flushes every 100 transactions (stream-append mode, not exit-only)
  - Writes CSV header on first file creation; skips header when appending to existing file
  - Handles OVERWRITE_CSV=true by truncating and re-writing the header
  - Thread-safety not required (single-threaded simulator)
"""
import csv
import os

CSV_FIELDNAMES = [
    "transaction_id",
    "user_id",
    "merchant_id",
    "amount",
    "currency",
    "merchant_category",
    "latitude",
    "longitude",
    "timestamp",
    "device_id",
    "is_international",
    "is_fraud",
]


class CSVWriter:
    """
    Buffered CSV writer. Accumulates transaction dicts in memory and flushes
    every 100 rows to the output file. Handles header-on-first-write logic.
    """

    def __init__(self, path: str, overwrite: bool, fieldnames: list) -> None:
        """
        Args:
            path:       Absolute or relative path to the CSV output file.
            overwrite:  If True, truncate existing file and rewrite header.
            fieldnames: List of column names for the CSV header and row ordering.
        """
        self.path = path
        self.fieldnames = fieldnames
        self.buffer: list[dict] = []

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        # Determine whether to write header and which open mode to use
        if overwrite or not os.path.exists(path) or os.path.getsize(path) == 0:
            # Write header now in write mode (truncates any existing file)
            with open(self.path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
            # All subsequent writes are appends
        # If file exists and is non-empty, skip header — just append

    def add(self, txn_dict: dict) -> None:
        """Buffer one transaction dict. Flushes automatically at 100 rows."""
        self.buffer.append(txn_dict)
        if len(self.buffer) >= 100:
            self._flush()

    def flush_remaining(self) -> None:
        """Flush partial buffer to disk. Call on SIGTERM shutdown."""
        if self.buffer:
            self._flush()

    def _flush(self) -> None:
        """Write all buffered rows to disk in append mode, then clear the buffer."""
        with open(self.path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerows(self.buffer)
        self.buffer.clear()
