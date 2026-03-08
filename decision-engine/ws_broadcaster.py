"""
ws_broadcaster.py — WebSocket broadcast server for live decision streaming.

Class:
    WSBroadcaster — starts sync websockets server, exposes broadcast()

WebSocket message schema (JSON string):
    {
      "transaction_id": str,
      "user_id": str,
      "amount": float,
      "fraud_probability": float,
      "risk_level": str,          # "LOW" | "MEDIUM" | "HIGH"
      "decision": str,            # "APPROVE" | "FLAG" | "BLOCK"
      "fired_rules": list[str],
      "timestamp": str            # ISO 8601 UTC
    }

All decisions are broadcast — dashboard filters client-side.
SHAP values are NOT included (fetched on demand via Phase 5 REST API).
"""
import json
import threading

import structlog
from websockets.sync.server import serve

log = structlog.get_logger(__name__)


class WSBroadcaster:
    def __init__(self) -> None:
        self._clients: set = set()
        self._lock = threading.Lock()
        self._server = None

    def start(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        """
        Start WebSocket server in a daemon thread.
        Must be called once at service startup before the Kafka consumer loop.
        """
        self._server = serve(self._handler, host, port)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        log.info("ws_server_started", host=host, port=port)

    def _handler(self, websocket) -> None:
        """
        Per-connection handler: add client, block until disconnect, remove client.
        Called by the websockets library in its own thread per connection.
        """
        with self._lock:
            self._clients.add(websocket)
        log.debug("ws_client_connected", total=len(self._clients))
        try:
            websocket.wait_closed()
        finally:
            with self._lock:
                self._clients.discard(websocket)
            log.debug("ws_client_disconnected", total=len(self._clients))

    def broadcast(self, message: dict) -> None:
        """
        Serialize message to JSON and send to all connected clients.
        Called from Kafka consumer thread for every decision (APPROVE + FLAG + BLOCK).
        Dead connections are removed silently.
        """
        payload = json.dumps(message)
        dead: set = set()
        with self._lock:
            clients_snapshot = set(self._clients)

        for client in clients_snapshot:
            try:
                client.send(payload)
            except Exception:
                dead.add(client)

        if dead:
            with self._lock:
                self._clients -= dead
            log.debug("ws_dead_clients_removed", count=len(dead))
