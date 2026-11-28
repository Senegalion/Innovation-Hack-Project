import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./smartlab.db")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./data/files"))
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_BUCKET = os.getenv("S3_BUCKET", "smartlab")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
USE_S3 = bool(S3_ENDPOINT or os.getenv("USE_S3"))
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "smartlab_docs")
EMBED_DIM = 384
SEGMENTATION_URL = os.getenv("SEGMENTATION_URL")
SEGMENTATION_METHOD = os.getenv("SEGMENTATION_METHOD", "geometric")
EMERGENCY_NUMBER = os.getenv("EMERGENCY_NUMBER", "112")
SEED_DEMO = os.getenv("SEED_DEMO", "1") == "1"

# AI assistant (Claude). "auto": on when ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is set; "1": always on (e.g. with
# an `ant auth login` profile); "0": off. Without it the keyword assistant answers.
AI_ENABLED = os.getenv("AI_ENABLED", "auto").strip().lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN")
AI_MODEL = os.getenv("AI_MODEL", "claude-opus-5-5")
AI_EFFORT = os.getenv("AI_EFFORT", "low")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "60"))

# MCP server: browser Origins allowed to call /mcp (requests without an Origin header, e.g. desktop clients, are
# always allowed). Comma-separated hostnames.
MCP_ALLOWED_ORIGINS = [h.strip() for h in os.getenv("MCP_ALLOWED_ORIGINS", "localhost,127.0.0.1").split(",") if h.strip()]
