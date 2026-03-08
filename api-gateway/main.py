"""
main.py — FastAPI API Gateway entry point.

Lifecycle:
    - Startup: create asyncpg pool, redis connection, start Kafka consumer task
    - Shutdown: cancel Kafka task, close pool and redis

Routes:
    GET  /health
    GET  /api/transactions/recent
    GET  /api/transactions/{id}
    GET  /api/metrics/summary
    GET  /api/stats/hourly
    POST /api/transactions/{id}/review
    WS   /ws/live
"""
from contextlib import asynccontextmanager
import asyncio
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncpg

import config
import db
import redis_client as redis_mod
from kafka_consumer import kafka_consumer_loop, manager
from routes.transactions import router as txn_router
from routes.metrics import router as met_router
from routes.review import router as rev_router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.pool = await db.create_pool(config.DATABASE_URL)
    app.state.redis = await redis_mod.create_redis(config.REDIS_URL)
    consumer_task = asyncio.create_task(kafka_consumer_loop())
    log.info("api_gateway_started", port=config.PORT)
    yield
    # Shutdown
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await app.state.pool.close()
    await redis_mod.close_redis(app.state.redis)
    log.info("api_gateway_stopped")


app = FastAPI(title="Fraud Detection API Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(txn_router, prefix="/api")
app.include_router(met_router, prefix="/api")
app.include_router(rev_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; data flows server->client only
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, log_level="info")
