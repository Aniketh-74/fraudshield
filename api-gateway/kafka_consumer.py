"""
kafka_consumer.py — aiokafka consumer loop that broadcasts decisions to WebSocket clients.

Exports:
    manager              — ConnectionManager singleton
    kafka_consumer_loop  — async coroutine; start via asyncio.create_task()
"""
import asyncio
import json
import structlog
from aiokafka import AIOKafkaConsumer
import config

log = structlog.get_logger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list = []

    async def connect(self, ws):
        await ws.accept()
        self.active_connections.append(ws)
        log.info("ws_client_connected", total=len(self.active_connections))

    def disconnect(self, ws):
        if ws in self.active_connections:
            self.active_connections.remove(ws)
        log.info("ws_client_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: str):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.active_connections.remove(d)


manager = ConnectionManager()


async def kafka_consumer_loop():
    while True:
        consumer = AIOKafkaConsumer(
            config.KAFKA_DECISIONS_TOPIC,
            bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
            group_id=config.KAFKA_GROUP_ID,
            auto_offset_reset="latest",  # live stream only — not replay
            value_deserializer=lambda v: v.decode("utf-8"),
        )
        try:
            await consumer.start()
            log.info("kafka_consumer_started", topic=config.KAFKA_DECISIONS_TOPIC, group=config.KAFKA_GROUP_ID)
            async for msg in consumer:
                await manager.broadcast(msg.value)
        except asyncio.CancelledError:
            log.info("kafka_consumer_cancelled")
            await consumer.stop()
            log.info("kafka_consumer_stopped")
            return
        except Exception as e:
            log.error("kafka_consumer_error", error=str(e), exc_info=True)
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
        log.info("kafka_consumer_restarting", delay_s=3)
        await asyncio.sleep(3)
