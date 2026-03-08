import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/frauddb")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_DECISIONS_TOPIC = os.getenv("KAFKA_DECISIONS_TOPIC", "decisions")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "api-gateway-group")
PORT = int(os.getenv("PORT", "8080"))
