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

# Automatic inspection reminders (certificates, services, verification checks). Items due within
# INSPECTION_WINDOW_DAYS are notified; the background check runs every INSPECTION_CHECK_HOURS (0 = off).
INSPECTION_WINDOW_DAYS = int(os.getenv("INSPECTION_WINDOW_DAYS", "14"))
INSPECTION_CHECK_HOURS = float(os.getenv("INSPECTION_CHECK_HOURS", "6"))
