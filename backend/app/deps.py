from datetime import date, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .db import SessionLocal, User


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ser(obj) -> dict:
    out = {}
    for c in inspect(obj).mapper.column_attrs:
        v = getattr(obj, c.key)
        out[c.key] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def name_of(db: Session, uid: str | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return u.name if u else None


def current_user(x_user_id: str | None = Header(None), db: Session = Depends(get_db)) -> User | None:
    return db.get(User, x_user_id) if x_user_id else None


ACCESS_RANK = {"worker": 0, "leader": 1, "admin": 2}


def require(level: str):
    def dep(user: User | None = Depends(current_user)) -> User:
        if not user:
            raise HTTPException(401, "Missing or unknown X-User-Id header")
        if ACCESS_RANK.get(user.access, 0) < ACCESS_RANK[level]:
            raise HTTPException(403, f"Requires {level} access")
        return user

    return dep


def first_name(name: str) -> str:
    return name.replace("Dr. ", "").split()[0]
