import logging
import time
from pathlib import Path

from .. import config

log = logging.getLogger("smartlab.storage")


class LocalStorage:
    backend = "local"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str):
        (self.root / key).unlink(missing_ok=True)


class S3Storage:
    backend = "s3"

    def __init__(self):
        import boto3

        self.bucket = config.S3_BUCKET
        self.client = boto3.client(
            "s3", endpoint_url=config.S3_ENDPOINT, region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY, aws_secret_access_key=config.S3_SECRET_KEY,
        )
        existing = {b["Name"] for b in self.client.list_buckets().get("Buckets", [])}
        if self.bucket not in existing:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage = None


def storage():
    global _storage
    if _storage is None:
        if config.USE_S3:
            for attempt in range(15):
                try:
                    _storage = S3Storage()
                    break
                except Exception as e:
                    if attempt == 14:
                        log.warning("S3 unavailable (%s), falling back to local storage", e)
                        _storage = LocalStorage(config.STORAGE_DIR)
                    else:
                        time.sleep(1)
        else:
            _storage = LocalStorage(config.STORAGE_DIR)
    return _storage
