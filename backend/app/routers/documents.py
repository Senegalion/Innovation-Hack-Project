from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import Document, DocumentChunk, SessionLocal, User
from ..deps import current_user, get_db, name_of, ser
from ..services.documents import process_document, search, store_upload
from ..services.gamification import award
from ..services.storage import storage

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD = 200 * 1024 * 1024


def doc_dict(db: Session, d: Document, full: bool = False) -> dict:
    out = {k: v for k, v in ser(d).items() if k not in ("text", "tables")}
    out.update({"uploaded_by_name": name_of(db, d.uploaded_by), "download_url": f"/api/documents/{d.id}/download",
                "chunks": db.query(DocumentChunk).filter_by(document_id=d.id).count(),
                "preview": d.text[:400]})
    if full:
        out.update({"text": d.text, "tables": d.tables})
    return out


def process_in_background(doc_id: int):
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc:
            process_document(db, doc)
    finally:
        db.close()


@router.post("/documents")
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...), lab_id: str | None = Form(None),
                          title: str | None = Form(None), kind: str | None = Form("auto"),
                          target_type: str | None = Form(None), target_id: str | None = Form(None),
                          process: bool = Form(True), db: Session = Depends(get_db),
                          user: User | None = Depends(current_user)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large")
    doc = store_upload(db, data, file.filename or "upload.bin", file.content_type or "application/octet-stream",
                       title, kind, lab_id, target_type, target_id, user.id if user else None)
    if user and doc.kind in ("manual", "sds"):
        award(db, user.id, "documentation", lab_id, f"uploaded {doc.title}")
    db.commit()
    if process and doc.kind not in ("image", "model", "pointcloud"):
        background.add_task(process_in_background, doc.id)
    else:
        doc.status = "stored"
        db.commit()
    return doc_dict(db, doc)


@router.get("/documents")
def list_documents(lab_id: str | None = None, target_id: str | None = None, kind: str | None = None,
                   db: Session = Depends(get_db)):
    q = db.query(Document)
    if lab_id:
        q = q.filter((Document.lab_id == lab_id) | (Document.lab_id.is_(None)))
    if target_id:
        q = q.filter_by(target_id=target_id)
    if kind:
        q = q.filter_by(kind=kind)
    return [doc_dict(db, d) for d in q.order_by(Document.at.desc()).all()]


@router.get("/documents/search")
def search_documents(q: str, lab_id: str | None = None, target_id: str | None = None, limit: int = 5,
                     db: Session = Depends(get_db)):
    return search(db, q, lab_id, target_id, limit)


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404)
    return doc_dict(db, d, full=True)


@router.get("/documents/{doc_id}/download")
def download(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404)
    try:
        data = storage().get(d.storage_key)
    except Exception as e:
        raise HTTPException(404, f"File missing in storage: {e}") from e
    return Response(data, media_type=d.content_type,
                    headers={"Content-Disposition": f'inline; filename="{d.filename}"'})


@router.post("/documents/{doc_id}/process")
def reprocess(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404)
    return doc_dict(db, process_document(db, d))


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404)
    if not user or (user.id != d.uploaded_by and user.access == "worker"):
        raise HTTPException(403, "Only the uploader or a leader can delete")
    try:
        storage().delete(d.storage_key)
    except Exception:
        pass
    db.query(DocumentChunk).filter_by(document_id=d.id).delete()
    db.delete(d)
    db.commit()
    return {"ok": True}
