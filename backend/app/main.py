import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import SEED_DEMO
from .db import init_db
from .realtime import hub
from .routers import admin, assets, documents, incidents, labs, optional, quests, social, spatial
from .seed import seed

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SMARTLAB Digital Twin API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (labs, assets, quests, social, incidents, admin, documents, spatial, optional):
    app.include_router(r.router)


@app.on_event("startup")
def startup():
    init_db()
    if SEED_DEMO:
        seed()


@app.get("/api/health")
def health():
    from .services.documents import qdrant
    from .services.storage import storage

    return {"ok": True, "storage": storage().backend, "vector_index": "qdrant" if qdrant() else "database"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.clients.discard(ws)
