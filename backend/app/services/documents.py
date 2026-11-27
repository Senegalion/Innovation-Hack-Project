import hashlib
import io
import logging
import math
import re
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from .. import config
from ..db import Document, DocumentChunk
from .storage import storage

log = logging.getLogger("smartlab.documents")

TEXT_TYPES = ("txt", "md", "csv", "json")
MODEL_TYPES = ("glb", "gltf", "obj", "ply", "pcd", "xyz", "las", "e57", "stl", "blend")
IMAGE_TYPES = ("png", "jpg", "jpeg", "webp", "gif")


def guess_kind(filename: str, declared: str | None) -> str:
    if declared and declared != "auto":
        return declared
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in MODEL_TYPES:
        return "pointcloud" if ext in ("ply", "pcd", "xyz", "las", "e57") else "model"
    if ext in IMAGE_TYPES:
        return "image"
    if "sds" in filename.lower():
        return "sds"
    if ext == "pdf":
        return "manual"
    return "other"


def store_upload(db: Session, data: bytes, filename: str, content_type: str, title: str | None, kind: str | None,
                 lab_id: str | None, target_type: str | None, target_id: str | None, user_id: str | None) -> Document:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "file"
    key = f"{lab_id or 'global'}/{uuid.uuid4().hex[:12]}-{safe}"
    storage().put(key, data, content_type)
    doc = Document(lab_id=lab_id, title=title or Path(filename).stem, filename=filename, content_type=content_type,
                   size=len(data), storage_key=key, kind=guess_kind(filename, kind), target_type=target_type,
                   target_id=target_id, uploaded_by=user_id)
    db.add(doc)
    db.flush()
    return doc


def extract_docling(data: bytes, filename: str) -> tuple[str, list, int]:
    from docling.document_converter import DocumentConverter

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_bytes(data)
        result = DocumentConverter().convert(str(path))
        doc = result.document
        text = doc.export_to_markdown()
        tables = []
        for t in getattr(doc, "tables", []):
            try:
                tables.append(t.export_to_dataframe().to_dict(orient="records"))
            except Exception:
                continue
        pages = len(getattr(doc, "pages", {}) or {})
        return text, tables, pages


def extract_pypdf(data: bytes) -> tuple[str, list, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n\n".join(pages), [], len(pages)


def extract(data: bytes, filename: str) -> tuple[str, list, int, str]:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in TEXT_TYPES:
        return data.decode("utf-8", errors="replace"), [], 1, "text"
    if ext in IMAGE_TYPES or ext in MODEL_TYPES:
        return "", [], 0, "none"
    try:
        text, tables, pages = extract_docling(data, filename)
        return text, tables, pages, "docling"
    except ImportError:
        pass
    except Exception as e:
        log.warning("docling failed for %s: %s", filename, e)
    if ext == "pdf":
        text, tables, pages = extract_pypdf(data)
        return text, tables, pages, "pypdf"
    return data.decode("utf-8", errors="replace"), [], 1, "text"


def chunk_text(text: str, size: int = 700, overlap: int = 120) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
            continue
        if cur:
            chunks.append(cur)
        while len(p) > size:
            chunks.append(p[:size])
            p = p[size - overlap:]
        cur = (chunks[-1][-overlap:] + "\n\n" + p) if chunks and overlap else p
    if cur:
        chunks.append(cur)
    return chunks


TOKEN = re.compile(r"[a-ząćęłńóśźż0-9\-]{2,}", re.I)


def tokens(text: str) -> list[str]:
    words = [w.lower() for w in TOKEN.findall(text)]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def embed(text: str, dim: int = config.EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    for t in tokens(text):
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_qdrant = None
_qdrant_failed = False


def qdrant():
    global _qdrant, _qdrant_failed
    if _qdrant is not None or _qdrant_failed or not config.QDRANT_URL:
        return _qdrant
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        client = QdrantClient(url=config.QDRANT_URL, timeout=5)
        names = {c.name for c in client.get_collections().collections}
        if config.QDRANT_COLLECTION not in names:
            client.create_collection(config.QDRANT_COLLECTION,
                                     vectors_config=VectorParams(size=config.EMBED_DIM, distance=Distance.COSINE))
        _qdrant = client
    except Exception as e:
        log.warning("Qdrant unavailable (%s); using database search", e)
        _qdrant_failed = True
    return _qdrant


def index_chunks(doc: Document, chunks: list[DocumentChunk]) -> bool:
    client = qdrant()
    if not client or not chunks:
        return False
    from qdrant_client.models import PointStruct

    try:
        client.upsert(config.QDRANT_COLLECTION, points=[
            PointStruct(id=c.id, vector=embed(c.text), payload={
                "document_id": doc.id, "lab_id": doc.lab_id, "title": doc.title, "kind": doc.kind,
                "target_id": doc.target_id, "text": c.text[:1000]}) for c in chunks])
        return True
    except Exception as e:
        log.warning("Qdrant upsert failed: %s", e)
        return False


def process_document(db: Session, doc: Document, data: bytes | None = None) -> Document:
    doc.status = "processing"
    try:
        data = data if data is not None else storage().get(doc.storage_key)
        text, tables, pages, processor = extract(data, doc.filename)
        doc.text, doc.tables, doc.pages, doc.processor = text, tables, pages, processor
        db.query(DocumentChunk).filter_by(document_id=doc.id).delete()
        chunks = [DocumentChunk(document_id=doc.id, idx=i, text=t) for i, t in enumerate(chunk_text(text))]
        db.add_all(chunks)
        db.flush()
        indexed = index_chunks(doc, chunks)
        doc.status = "processed"
        doc.error = "" if indexed or not chunks or not config.QDRANT_URL else "vector index unavailable"
    except Exception as e:
        doc.status, doc.error = "failed", str(e)
    db.commit()
    return doc


def search(db: Session, query: str, lab_id: str | None = None, target_id: str | None = None,
           limit: int = 5) -> dict:
    client = qdrant()
    if client:
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            must = []
            if lab_id:
                must.append(FieldCondition(key="lab_id", match=MatchValue(value=lab_id)))
            if target_id:
                must.append(FieldCondition(key="target_id", match=MatchValue(value=target_id)))
            hits = client.search(config.QDRANT_COLLECTION, query_vector=embed(query), limit=limit,
                                 query_filter=Filter(must=must) if must else None)
            return {"engine": "qdrant", "results": [
                {"document_id": h.payload["document_id"], "title": h.payload["title"], "kind": h.payload["kind"],
                 "target_id": h.payload.get("target_id"), "score": round(h.score, 3), "text": h.payload["text"]}
                for h in hits if h.score > 0.05]}
        except Exception as e:
            log.warning("Qdrant search failed: %s", e)
    q = set(tokens(query))
    qv = embed(query)
    results = []
    rows = db.query(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
    if lab_id:
        rows = rows.filter((Document.lab_id == lab_id) | (Document.lab_id.is_(None)))
    if target_id:
        rows = rows.filter(Document.target_id == target_id)
    for chunk, doc in rows.all():
        overlap = len(q & set(tokens(chunk.text)))
        if not overlap:
            continue
        score = sum(a * b for a, b in zip(qv, embed(chunk.text)))
        results.append({"document_id": doc.id, "title": doc.title, "kind": doc.kind, "target_id": doc.target_id,
                        "score": round(score, 3), "text": chunk.text[:1000]})
    results.sort(key=lambda r: -r["score"])
    return {"engine": "database", "results": results[:limit]}
