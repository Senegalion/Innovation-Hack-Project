import re

from sqlalchemy.orm import Session

from ..db import Equipment, Lab, Material, Sample, Space, User, Workstation
from ..i18n import DEFAULT_LANG, tr
from .documents import search

STOPWORDS = {"gdzie", "jest", "znajduje", "się", "sie", "where", "the", "what", "find", "jaki", "jaka", "jakie",
             "pokaż", "pokaz", "show", "odczynnik", "urządzenie", "urzadzenie", "reagent", "device", "mamy"}

PAIRS = [
    ("acetonitryl", "acetonitrile"), ("metanol", "methanol"), ("etanol", "ethanol"), ("kwas", "acid"),
    ("mrówkowy", "formic"), ("mrowkowy", "formic"), ("trypsyna", "trypsin"), ("wodorotlenek", "hydroxide"),
    ("sodu", "sodium"), ("zamrażarka", "freezer"), ("zamrazarka", "freezer"), ("lodówka", "fridge"),
    ("lodowka", "fridge"), ("wirówka", "centrifuge"), ("wirowka", "centrifuge"), ("waga", "balance"),
    ("mikroskop", "microscope"), ("inkubator", "incubator"), ("dygestorium", "hood"), ("wyciąg", "hood"),
    ("szafa", "cabinet"), ("szafka", "cabinet"), ("spektrometr", "spectrometer"), ("chromatograf", "chromatograph"),
    ("stół", "workbench"), ("stanowisko", "workbench"), ("prysznic", "shower"), ("oczomyjka", "eyewash"),
    ("myjka", "eyewash"), ("apteczka", "first aid"), ("gaśnica", "extinguisher"), ("gasnica", "extinguisher"),
    ("wyjście", "exit"), ("wyjscie", "exit"), ("próbka", "sample"), ("probka", "sample"), ("strefa", "zone"),
    ("autoklaw", "autoclave"), ("bufor", "buffer"), ("osocze", "plasma"), ("agar", "agar"), ("bulion", "broth"),
    ("łatwopalne", "flammables"), ("kriogeniczna", "cryogenic"), ("chemiczna", "chemical"),
]
VARIANTS: dict[str, set[str]] = {}
for a, b in PAIRS:
    VARIANTS.setdefault(a, {a}).add(b)
    VARIANTS.setdefault(b, {b}).add(a)


def normalize(question: str) -> list[set[str]]:
    out = []
    for w in re.findall(r"[\w\-]+", question.lower()):
        if w in STOPWORDS or len(w) <= 2:
            continue
        variants = VARIANTS.get(w, {w})
        out.append({v for x in variants for v in x.split() if len(v) > 2})
    return out


def ask_assistant(db: Session, lab_id: str, question: str, lang: str = DEFAULT_LANG) -> dict:
    words = normalize(question)
    lab = db.get(Lab, lab_id)
    hits = []

    def score(hay: str) -> int:
        hay = hay.lower()
        return sum(1 for variants in words if any(v in hay for v in variants))

    for e in db.query(Equipment).filter_by(lab_id=lab_id):
        if s := score(f"{e.id} {e.name} {e.category}"):
            hits.append((s, "equipment", e.id))
    for w in db.query(Workstation).filter_by(lab_id=lab_id):
        if s := score(f"{w.id} {w.name} workbench workstation stanowisko"):
            hits.append((s, "equipment", w.id))
    for m in db.query(Material).filter_by(lab_id=lab_id):
        if s := score(f"{m.id} {m.name} {m.cas} {m.catalog_no}"):
            hits.append((s + 0.5, "material", m.id))
    for smp in db.query(Sample).filter_by(lab_id=lab_id):
        if s := score(f"{smp.id} {smp.label} sample próbka"):
            hits.append((s, "sample", smp.id))
    for p in lab.points:
        if s := score(f"{p['kind']} {p['label']}"):
            hits.append((s + 1, "point", p["id"]))
    for sp in db.query(Space).filter_by(lab_id=lab_id):
        if s := score(f"{sp.name} {sp.hazard} zone strefa"):
            hits.append((s, "space", sp.id))

    query = " ".join(sorted({v for variants in words for v in variants}))
    docs = search(db, query, lab_id=lab_id, limit=2) if words else {"results": []}
    doc_hits = [{"document_id": d["document_id"], "title": d["title"], "excerpt": d["text"][:240]}
                for d in docs["results"]]

    if not hits:
        answer = tr(lang, "as.docOnly", title=doc_hits[0]["title"]) if doc_hits else tr(lang, "as.none")
        return {"answer": answer, "highlight": None, "documents": doc_hits, "matches": []}

    hits.sort(key=lambda h: -h[0])
    _, kind, hid = hits[0]
    matches = [{"type": k, "id": i} for _, k, i in hits[:5]]
    base = {"documents": doc_hits, "matches": matches}
    if kind == "equipment":
        e = db.get(Equipment, hid) or db.get(Workstation, hid)
        resp = db.get(User, e.responsible_id) if e.responsible_id else None
        answer = (tr(lang, "as.equipment", name=e.name, status=tr(lang, f"status.{e.status}"))
                  + (tr(lang, "as.responsible", name=resp.name) if resp else "")
                  + (tr(lang, "as.note", note=e.notes) if e.notes else ""))
        return {**base, "answer": answer, "highlight": hid}
    if kind == "material":
        m = db.get(Material, hid)
        loc = db.get(Equipment, m.location_id)
        answer = tr(lang, "as.material", name=m.name, qty=m.quantity, unit=m.unit, lot=m.lot,
                    location=loc.name if loc else m.location_id, expires=m.expires)
        return {**base, "answer": answer, "highlight": m.location_id, "material": hid}
    if kind == "sample":
        smp = db.get(Sample, hid)
        owner = db.get(User, smp.owner_id)
        answer = tr(lang, "as.sample", id=smp.id, label=smp.label, status=smp.status, location=smp.location_id,
                    owner=tr(lang, "as.owner", name=owner.name) if owner else "")
        return {**base, "answer": answer, "highlight": smp.location_id}
    if kind == "space":
        sp = db.get(Space, hid)
        state = "closed" if sp.closed else "restricted" if sp.restricted else "open"
        answer = tr(lang, "as.space", name=sp.name, state=tr(lang, f"as.state.{state}"),
                    hazard=f", {sp.hazard}" if sp.hazard else "")
        return {**base, "answer": answer, "highlight": None, "point": hid}
    p = next(p for p in lab.points if p["id"] == hid)
    return {**base, "answer": tr(lang, "as.point", label=p["label"]), "highlight": None, "point": hid}
