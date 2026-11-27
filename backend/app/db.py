from datetime import date, datetime

import logging

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL, SEED_DEMO

SCHEMA_VERSION = "3"
log = logging.getLogger("smartlab.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    access: Mapped[str] = mapped_column(String, default="worker")
    description: Mapped[str] = mapped_column(Text, default="")
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    initials: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    access: Mapped[str] = mapped_column(String, default="worker")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    online: Mapped[int] = mapped_column(Integer, default=1)
    lab_id: Mapped[str] = mapped_column(String)
    mentor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    onboarding_done: Mapped[int] = mapped_column(Integer, default=0)
    joined: Mapped[date | None] = mapped_column(Date, nullable=True)


class Lab(Base):
    __tablename__ = "labs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    building: Mapped[str] = mapped_column(String)
    manager_id: Mapped[str] = mapped_column(String)
    width: Mapped[float] = mapped_column(Float)
    depth: Mapped[float] = mapped_column(Float)
    entrance: Mapped[list] = mapped_column(JSON)
    glb_url: Mapped[str | None] = mapped_column(String, nullable=True)
    points: Mapped[list] = mapped_column(JSON, default=list)
    floorplan: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Space(Base):
    __tablename__ = "spaces"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("labs.id"))
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="zone")
    x: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    w: Mapped[float] = mapped_column(Float)
    d: Mapped[float] = mapped_column(Float)
    hazard: Mapped[str] = mapped_column(String, default="")
    restricted: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[int] = mapped_column(Integer, default=0)
    access_roles: Mapped[list] = mapped_column(JSON, default=list)


class Workstation(Base):
    __tablename__ = "workstations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("labs.id"))
    space_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String)
    x: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    w: Mapped[float] = mapped_column(Float)
    d: Mapped[float] = mapped_column(Float)
    h: Mapped[float] = mapped_column(Float, default=0.9)
    status: Mapped[str] = mapped_column(String, default="ok")
    responsible_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Equipment(Base):
    __tablename__ = "machines"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("labs.id"))
    workstation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ok")
    x: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    w: Mapped[float] = mapped_column(Float)
    d: Mapped[float] = mapped_column(Float)
    h: Mapped[float] = mapped_column(Float)
    serial: Mapped[str] = mapped_column(String, default="")
    storage_class: Mapped[str | None] = mapped_column(String, nullable=True)
    responsible_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_check: Mapped[date | None] = mapped_column(Date, nullable=True)
    uncertainty: Mapped[str] = mapped_column(String, default="")
    last_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    cert_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    inspection_interval_days: Mapped[int] = mapped_column(Integer, default=180)
    reading: Mapped[str] = mapped_column(String, default="")
    manual: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("labs.id"))
    name: Mapped[str] = mapped_column(String)
    cas: Mapped[str] = mapped_column(String, default="")
    catalog_no: Mapped[str] = mapped_column(String, default="")
    lot: Mapped[str] = mapped_column(String, default="")
    location_id: Mapped[str] = mapped_column(String)
    storage_requirement: Mapped[str] = mapped_column(String, default="general")
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    min_stock: Mapped[float] = mapped_column(Float)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=5)
    unit_cost_eur: Mapped[float] = mapped_column(Float, default=0)
    delivered: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires: Mapped[date | None] = mapped_column(Date, nullable=True)
    hazards: Mapped[list] = mapped_column(JSON, default=list)
    sds: Mapped[int] = mapped_column(Integer, default=1)
    responsible_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    experiment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    location_id: Mapped[str] = mapped_column(String)
    owner_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="stored")
    collected: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("labs.id"))
    code: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    lead_id: Mapped[str] = mapped_column(String)
    members: Mapped[list] = mapped_column(JSON, default=list)
    dates: Mapped[list] = mapped_column(JSON)
    usage: Mapped[list] = mapped_column(JSON)
    equipment_ids: Mapped[list] = mapped_column(JSON, default=list)


class Quest(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, default="daily")
    priority: Mapped[str] = mapped_column(String, default="medium")
    xp: Mapped[int] = mapped_column(Integer, default=20)
    minutes: Mapped[int] = mapped_column(Integer, default=10)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    material_id: Mapped[str | None] = mapped_column(String, nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    problem: Mapped[str] = mapped_column(Text, default="")
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    tpl: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_type: Mapped[str] = mapped_column(String, index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    lab_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    members: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String, index=True)
    sender_id: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    equipment_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    share: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    mentions: Mapped[list] = mapped_column(JSON, default=list)
    help_request: Mapped[int] = mapped_column(Integer, default=0)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_id: Mapped[str] = mapped_column(String)
    equipment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reporter_id: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    priority: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    anonymous: Mapped[int] = mapped_column(Integer, default=0)
    x: Mapped[float | None] = mapped_column(Float, nullable=True)
    z: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    cause: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolver_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notified: Mapped[list] = mapped_column(JSON, default=list)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    ref_type: Mapped[str | None] = mapped_column(String, nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String, nullable=True)
    read: Mapped[int] = mapped_column(Integer, default=0)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String, default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="other")
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="uploaded")
    processor: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    tables: Mapped[list] = mapped_column(JSON, default=list)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class PointRule(Base):
    __tablename__ = "point_rules"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String)
    points: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String, default="xp")
    active: Mapped[int] = mapped_column(Integer, default=1)


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String)
    target: Mapped[int] = mapped_column(Integer)
    starts: Mapped[date] = mapped_column(Date)
    ends: Mapped[date] = mapped_column(Date)
    reward_xp: Mapped[int] = mapped_column(Integer, default=50)
    rewarded: Mapped[int] = mapped_column(Integer, default=0)


class Reconstruction(Base):
    __tablename__ = "reconstructions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_id: Mapped[str] = mapped_column(String)
    document_id: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String, default="geometric")
    up_axis: Mapped[str] = mapped_column(String, default="y")
    status: Mapped[str] = mapped_column(String, default="queued")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SchemaMeta(Base):
    __tablename__ = "schema_meta"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


def schema_outdated() -> bool:
    tables = set(inspect(engine).get_table_names())
    if not tables:
        return False
    if "schema_meta" not in tables:
        return True
    with SessionLocal() as s:
        row = s.get(SchemaMeta, "version")
        return not row or row.value != SCHEMA_VERSION


def init_db():
    if schema_outdated():
        if not SEED_DEMO:
            raise RuntimeError(f"Database schema is outdated (expected v{SCHEMA_VERSION}); migrate or reset it")
        log.warning("Outdated demo schema detected, recreating database with fresh demo data")
        old = MetaData()
        old.reflect(engine)
        old.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        s.merge(SchemaMeta(key="version", value=SCHEMA_VERSION))
        s.commit()
