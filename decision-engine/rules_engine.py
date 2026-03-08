"""
rules_engine.py — YAML-configured business rules with watchdog hot-reload.

Classes:
    RulesEngine  — loads rules.yaml, evaluates per-transaction, hot-reloads on file change

Usage:
    engine = RulesEngine(config.RULES_CONFIG_PATH)
    fired = engine.evaluate(features)   # list of fired rule names
"""
import threading
from pathlib import Path

import structlog
import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

log = structlog.get_logger(__name__)


class RulesEngine:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._rules: list[dict] = []
        self._load()
        self._start_watcher()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, features: dict) -> list[str]:
        """
        Evaluate all enabled rules against features dict.
        Returns list of fired rule names (empty list if none fire).
        features must already contain is_international (default 0 if absent).
        """
        with self._lock:
            rules_snapshot = list(self._rules)

        fired: list[str] = []
        for rule in rules_snapshot:
            if not rule.get("enabled", True):
                continue
            try:
                if self._eval_condition(rule["condition"], features):
                    fired.append(rule["name"])
            except Exception as e:
                log.warning(
                    "rule_eval_error",
                    rule=rule.get("name"),
                    error=str(e),
                )
        return fired

    # ------------------------------------------------------------------
    # Internal: loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._path) as f:
                data = yaml.safe_load(f)
            rules = data.get("rules", [])
            with self._lock:
                self._rules = rules
            log.info("rules_loaded", count=len(rules), path=self._path)
        except FileNotFoundError:
            log.error("rules_file_not_found", path=self._path)
            # Keep last-known-good rules (empty list on first load failure)
        except yaml.YAMLError as e:
            log.error("rules_yaml_parse_error", error=str(e), path=self._path)
            # Keep last-known-good rules

    def _start_watcher(self) -> None:
        parent_dir = str(Path(self._path).parent)
        filename = Path(self._path).name

        class _Handler(FileSystemEventHandler):
            def __init__(self_inner, reload_fn, target_filename: str) -> None:
                self_inner._reload = reload_fn
                self_inner._target = target_filename

            def on_modified(self_inner, event) -> None:
                if not event.is_directory and Path(event.src_path).name == self_inner._target:
                    log.info("rules_file_modified", path=event.src_path)
                    self_inner._reload()

        handler = _Handler(self._load, filename)
        observer = Observer()
        observer.schedule(handler, path=parent_dir, recursive=False)
        observer.daemon = True
        observer.start()
        log.info("rules_watcher_started", watching=parent_dir, file=filename)

    # ------------------------------------------------------------------
    # Internal: evaluation
    # ------------------------------------------------------------------

    def _eval_condition(self, cond: dict, features: dict) -> bool:
        if "all" in cond:
            return self._eval_all(cond, features)
        return self._eval_simple(cond, features)

    def _eval_simple(self, cond: dict, features: dict) -> bool:
        field = cond["field"]
        operator = cond["operator"]
        value = cond["value"]
        feature_value = features.get(field, 0.0)

        if operator == ">":
            return float(feature_value) > float(value)
        elif operator == "<":
            return float(feature_value) < float(value)
        elif operator == ">=":
            return float(feature_value) >= float(value)
        elif operator == "<=":
            return float(feature_value) <= float(value)
        elif operator == "==":
            return float(feature_value) == float(value)
        elif operator == "in":
            return float(feature_value) in [float(v) for v in value]
        else:
            log.warning("unknown_operator", operator=operator, field=field)
            return False

    def _eval_all(self, cond: dict, features: dict) -> bool:
        return all(self._eval_condition(sub, features) for sub in cond["all"])
