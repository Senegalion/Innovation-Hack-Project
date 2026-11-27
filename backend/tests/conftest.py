import os
import tempfile

TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{TMP}/test.db")
os.environ["STORAGE_DIR"] = f"{TMP}/files"
for key in ("QDRANT_URL", "S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET", "USE_S3"):
    os.environ.pop(key, None)
    if os.getenv(f"TEST_{key}"):
        os.environ[key] = os.environ[f"TEST_{key}"]

from app.db import Base, engine

Base.metadata.drop_all(engine)
