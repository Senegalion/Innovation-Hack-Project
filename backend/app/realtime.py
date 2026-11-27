from fastapi import WebSocket
from sqlalchemy.orm import Session

from .db import Notification


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.pending: list[dict] = []

    async def send(self, payload: dict):
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                self.clients.discard(ws)

    def queue(self, payload: dict):
        self.pending.append(payload)

    async def flush(self):
        items, self.pending = self.pending, []
        for p in items:
            await self.send(p)


hub = Hub()


def notify(db: Session, user_ids, kind: str, title: str, body: str = "", ref_type: str | None = None,
           ref_id: str | None = None, exclude: str | None = None) -> list[str]:
    sent = []
    for uid in dict.fromkeys(u for u in user_ids if u and u != exclude):
        n = Notification(user_id=uid, kind=kind, title=title, body=body, ref_type=ref_type,
                         ref_id=str(ref_id) if ref_id is not None else None)
        db.add(n)
        sent.append(uid)
        hub.queue({"type": "notification", "user_id": uid, "kind": kind, "title": title, "body": body,
                   "ref_type": ref_type, "ref_id": n.ref_id})
    return sent
