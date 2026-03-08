"""
conftest.py — Unit test configuration.

Pre-mocks heavy third-party modules (confluent_kafka, websockets) that are not
installed in the unit test environment and should not be required for pure unit
tests. This allows importing pure-logic functions from service modules without
needing running infrastructure.

Only modules that are NOT available in the test environment are mocked here.
Modules like redis, structlog, yaml, psycopg2 are installed via pip and do not
need mocking.
"""
import sys
from unittest.mock import MagicMock

# --- Mock confluent_kafka (requires native librdkafka, not installable without C compiler) ---
_confluent_kafka_mock = MagicMock()
_confluent_kafka_mock.Consumer = MagicMock
_confluent_kafka_mock.Producer = MagicMock
_confluent_kafka_mock.KafkaException = Exception
_confluent_kafka_mock.KafkaError = MagicMock()
_confluent_kafka_mock.KafkaError._PARTITION_EOF = -191
sys.modules["confluent_kafka"] = _confluent_kafka_mock

# --- Mock websockets (decision-engine ws_broadcaster imports websockets.sync.server) ---
_ws_mock = MagicMock()
_ws_sync_mock = MagicMock()
_ws_sync_server_mock = MagicMock()
_ws_sync_server_mock.serve = MagicMock()
_ws_sync_mock.server = _ws_sync_server_mock
_ws_mock.sync = _ws_sync_mock
sys.modules["websockets"] = _ws_mock
sys.modules["websockets.sync"] = _ws_sync_mock
sys.modules["websockets.sync.server"] = _ws_sync_server_mock

# --- Mock prometheus_client (ml-scorer metrics imports it at module level) ---
_prometheus_mock = MagicMock()
_prometheus_mock.Histogram = MagicMock(return_value=MagicMock())
_prometheus_mock.Counter = MagicMock(return_value=MagicMock())
_prometheus_mock.Gauge = MagicMock(return_value=MagicMock())
_prometheus_mock.CollectorRegistry = MagicMock()
_prometheus_mock.make_asgi_app = MagicMock()
sys.modules["prometheus_client"] = _prometheus_mock
