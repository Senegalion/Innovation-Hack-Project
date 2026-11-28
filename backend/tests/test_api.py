import io
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN = {"X-User-Id": "u-anna"}
LEADER = {"X-User-Id": "u-ewa"}
INTERN = {"X-User-Id": "u-tomek"}


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def wait_for(c, url, key, done_values, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = c.get(url).json()
        if r[key] in done_values:
            return r
        time.sleep(0.2)
    raise AssertionError(f"{url} did not finish: {r}")


def test_lab_has_spec_entities(c):
    lab = c.get("/api/labs/lab-204").json()
    ids = {e["id"] for e in lab["equipment"]}
    assert {"WB-1", "HPLC-04", "FRZ-80"} <= ids
    assert "WB-1" in lab["workstations"]
    assert any(s["id"] == "z-cryo" and s["restricted"] for s in lab["spaces"])
    assert c.get("/api/roles").json()


def test_material_forecast_and_anomalies(c):
    lab = c.get("/api/labs/lab-204").json()
    mats = {m["id"]: m["forecast"] for m in lab["materials"]}
    assert mats["MAT-ACN"]["order_by"] and "reorder" in mats["MAT-ACN"]["alerts"]
    assert "wrong_location" in mats["MAT-FA"]["alerts"]
    assert "quantity_mismatch" in mats["MAT-PBS"]["alerts"]
    assert "missing_sds" in mats["MAT-PLASMA"]["alerts"]


def test_quests_generated_and_personalized(c):
    board = c.get("/api/quests", params={"lab_id": "lab-204", "user_id": "u-tomek"}).json()
    titles = [q["title"] for q in board["pool"]]
    assert any(t.startswith("Przenieś Kwas mrówkowy") for t in titles)
    assert any(t.startswith("Przelicz ponownie Bufor PBS") for t in titles)
    assert any(t.startswith("Kontrola prewencyjna: Wirówka") for t in titles)
    assert any(q["reason"] for q in board["pool"])
    assert board["challenges"]


def test_quest_permissions_and_actions(c):
    r = c.post("/api/quests", json={"lab_id": "lab-204", "title": "x"}, headers=INTERN)
    assert r.status_code == 403
    q = c.post("/api/quests", json={"lab_id": "lab-204", "title": "Calibrate pipettes", "assignee_id": "u-kasia"},
               headers=LEADER).json()
    assert q["status"] == "accepted"
    notes = c.get("/api/notifications", params={"user_id": "u-kasia"}).json()
    assert any(n["kind"] == "quest_assigned" for n in notes)
    r = c.post(f"/api/quests/{q['id']}/action", json={"user_id": "u-kasia", "action": "delegate"}).json()
    assert r["assignee_id"] in ("u-ewa", "u-anna")
    r = c.post(f"/api/quests/{q['id']}/action", json={"user_id": "u-ewa", "action": "complete"}).json()
    assert r["xp"] == 20


def test_route_respects_restricted_area(c):
    intern = c.post("/api/route", json={"lab_id": "lab-204", "stops": ["FRZ-80", "WB-1"]}, headers=INTERN).json()
    assert any(u["id"] == "FRZ-80" for u in intern["unreachable"])
    assert intern["order"] == ["WB-1"]
    engineer = c.post("/api/route", json={"lab_id": "lab-204", "stops": ["FRZ-80", "WB-1"]},
                      headers={"X-User-Id": "u-michal"}).json()
    assert set(engineer["order"]) == {"FRZ-80", "WB-1"} and engineer["distance_m"] > 0


def test_route_with_closed_space(c):
    c.put("/api/labs/lab-204/spaces/z-block", headers=ADMIN,
          json={"id": "z-block", "name": "Closed corridor", "x": 10, "z": 7.75, "w": 20, "d": 0.5, "closed": 1})
    r = c.post("/api/route", json={"lab_id": "lab-204", "stops": ["CAB-F"]}, headers=ADMIN).json()
    assert r["unreachable"] and r["unreachable"][0]["id"] == "CAB-F"
    c.delete("/api/labs/lab-204/spaces/z-block", headers=ADMIN)


def test_floorplan_from_pointcloud_and_segmentation(c):
    ply = c.get("/api/labs/lab-204/export/pointcloud.ply", params={"points": 30000}).content
    glb = c.get("/api/labs/lab-204/export/model.glb").content
    assert glb[:4] == b"glTF"
    fp = c.post("/api/labs/lab-204/floorplan/from-model", headers=LEADER, data={"apply": "false"},
                files={"file": ("scan.ply", ply, "application/octet-stream")}).json()
    assert fp["occupied_ratio"] > 0.05 and fp["width"] > 15
    rec = c.post("/api/labs/lab-204/reconstructions", headers=LEADER, data={"method": "sam3d"},
                 files={"file": ("scan.ply", ply, "application/octet-stream")}).json()
    done = wait_for(c, f"/api/reconstructions/{rec['id']}", "status", ("done", "failed"))
    assert done["status"] == "done", done["error"]
    res = done["result"]
    assert res["method"] == "geometric" and res["notes"]
    assert res["matched"] >= 10 and res["unmatched"] <= 3
    svg = c.get("/api/labs/lab-204/floorplan", params={"format": "svg"})
    assert svg.text.startswith("<svg")


def test_documents_pipeline_and_search(c):
    r = c.get("/api/documents/search", params={"q": "odpowietrz pompy ciśnienia", "lab_id": "lab-204"}).json()
    assert r["results"] and r["results"][0]["title"] == "HPLC-04 — instrukcja obsługi"
    up = c.post("/api/documents", headers=INTERN, data={"lab_id": "lab-204", "target_id": "CF-03", "kind": "manual"},
                files={"file": ("cf03.txt", io.BytesIO(b"Centrifuge rotor must be balanced.\n\nMax 12000 rpm."),
                                "text/plain")}).json()
    doc = wait_for(c, f"/api/documents/{up['id']}", "status", ("processed", "failed"))
    assert doc["status"] == "processed" and doc["chunks"] >= 1
    assert c.get(f"/api/documents/{up['id']}/download").content.startswith(b"Centrifuge")
    hits = c.get("/api/documents/search", params={"q": "rotor balanced", "target_id": "CF-03"}).json()
    assert hits["results"]


def test_incident_escalation_and_knowledge(c):
    r = c.post("/api/incidents", json={"lab_id": "lab-204", "reporter_id": "u-tomek", "category": "spill",
                                       "priority": "critical", "description": "Acetonitrile spill",
                                       "equipment_id": "CAB-F"}).json()
    assert r["procedure"]["nearest"] and r["procedure"]["emergency_number"]
    assert "u-anna" in r["notified"] and "u-piotr" in r["notified"]
    assert c.post(f"/api/incidents/{r['id']}/resolve", json={"user_id": "u-tomek", "resolution": "x"}).status_code == 403
    c.post(f"/api/incidents/{r['id']}/resolve",
           json={"user_id": "u-piotr", "resolution": "Absorbed with spill kit", "cause": "Bottle knocked over"})
    kb = c.get("/api/knowledge", params={"lab_id": "lab-204", "q": "spill"}).json()
    assert any(k["cause"] == "Bottle knocked over" for k in kb)


def test_intern_alert_and_help(c):
    c.post("/api/equipment/MIC-01/logs", json={"user_id": "u-tomek", "kind": "use", "note": "first try"})
    notes = c.get("/api/notifications", params={"user_id": "u-ewa"}).json()
    assert any(n["kind"] == "intern_activity" for n in notes)
    board = c.get("/api/quests", params={"lab_id": "lab-204", "user_id": "u-michal"}).json()
    assert any("pierwszym użyciu: Mikroskop" in q["title"] for q in board["pool"])
    r = c.post("/api/help", json={"user_id": "u-tomek", "equipment_id": "HPLC-04", "text": "Pump won't prime"}).json()
    assert r["helpers"][0]["user_id"] == "u-michal"


def test_chat_groups_mentions_and_attachments(c):
    ch = c.post("/api/channels", json={"lab_id": "lab-204", "name": "Calibration crew", "members": ["u-piotr"]},
                headers=LEADER).json()
    c.post(f"/api/channels/{ch['id']}/invite", json={"user_ids": ["u-kasia"]}, headers=LEADER)
    doc = c.post("/api/documents", data={"kind": "image"},
                 files={"file": ("photo.png", b"\x89PNG fake", "image/png")}).json()
    m = c.post("/api/messages", json={"channel": ch["id"], "sender_id": "u-ewa", "text": "@service see photo",
                                      "attachments": [doc["id"]], "share": {"type": "machine", "id": "SP-02"}}).json()
    assert "u-piotr" in m["mentions"] and m["attachments"][0]["url"].endswith("/download")
    assert c.post("/api/messages", json={"channel": ch["id"], "sender_id": "u-tomek", "text": "hi"}).status_code == 403


def test_materials_inventory_actions(c):
    r = c.post("/api/materials/MAT-FA/logs", json={"user_id": "u-kasia", "kind": "move", "location_id": "CAB-F"}).json()
    assert r["storage_issue"] is None
    c.post("/api/materials/MAT-PBS/logs", json={"user_id": "u-kasia", "kind": "check", "observed": 2.4})
    assert "quantity_mismatch" in c.get("/api/materials/MAT-PBS").json()["forecast"]["alerts"]
    c.post("/api/materials/MAT-PBS/logs", json={"user_id": "u-kasia", "kind": "check", "observed": 2.4})
    m = c.get("/api/materials/MAT-PBS").json()
    assert "quantity_mismatch" not in m["forecast"]["alerts"]
    c.post("/api/materials/MAT-TRY/logs", json={"user_id": "u-ewa", "kind": "use_before_expiry", "amount": 2})
    stats = c.get("/api/admin/stats", params={"lab_id": "lab-204"}).json()
    assert stats["esg"]["saved_by_using_before_expiry_eur"] == 120
    assert stats["competence"] and stats["hotspots"]


def test_samples_qr_and_scan(c):
    s = c.post("/api/samples", json={"lab_id": "lab-204", "label": "New tube", "location_id": "SR-01",
                                     "owner_id": "u-michal"}).json()
    assert c.get(f"/api/scan/{s['id'].lower()}").json()["type"] == "sample"
    c.patch(f"/api/samples/{s['id']}", json={"user_id": "u-michal", "location_id": "FRZ-80", "status": "stored"})
    detail = c.get(f"/api/samples/{s['id']}").json()
    assert detail["location_id"] == "FRZ-80" and detail["history"]
    assert c.get(f"/api/qr/{s['id']}.svg").text.startswith("<svg")
    scan = c.get("/api/scan/HPLC-04", headers=INTERN).json()
    assert scan["quests"]


def test_admin_configuration(c):
    assert c.put("/api/point-rules/hazard_report", json={"points": 50}, headers=INTERN).status_code == 403
    assert c.put("/api/point-rules/hazard_report", json={"points": 50}, headers=ADMIN).json()["points"] == 50
    u = c.post("/api/users", json={"id": "u-new", "name": "Nowa Osoba", "role": "intern", "lab_id": "lab-204",
                                   "mentor_id": "u-ewa"}, headers=ADMIN).json()
    assert u["access"] == "worker"
    ob = c.get("/api/onboarding/u-new").json()
    assert ob["mentor"]["id"] == "u-ewa" and ob["who_does_what"]
    a = c.post("/api/labs/lab-204/assets", headers=ADMIN, json={"id": "PH-01", "name": "pH meter", "x": 13, "z": 10,
                                                                "w": 0.3, "d": 0.3, "h": 0.3}).json()
    assert a["id"] == "PH-01"
    assert c.delete("/api/assets/PH-01", headers=ADMIN).json()["ok"]


def test_assistant_polish_and_docs(c):
    r = c.post("/api/assistant", json={"lab_id": "lab-204", "question": "gdzie jest acetonitryl?"}).json()
    assert r["highlight"] == "CAB-F" and r["documents"]


def test_language_rendering(c):
    en = c.get("/api/quests", params={"lab_id": "lab-204", "user_id": "u-tomek"},
               headers={"Accept-Language": "en"}).json()
    pl = c.get("/api/quests", params={"lab_id": "lab-204", "user_id": "u-tomek"}).json()
    assert any(q["title"].startswith("Move Kwas mrówkowy to correct storage") for q in en["pool"])
    assert any(q["title"].startswith("Przenieś Kwas mrówkowy") for q in pl["pool"])
    assert any(q["reason"] and "same spot as" in q["reason"] for q in en["pool"])
    helpers = c.get("/api/help/HPLC-04", headers={"Accept-Language": "en"}).json()
    assert any("responsible for the device" in h["reasons"] for h in helpers)
    r = c.post("/api/assistant", json={"lab_id": "lab-204", "question": "where is acetonitrile?"},
               headers={"Accept-Language": "en"}).json()
    assert r["highlight"] == "CAB-F" and "is stored in" in r["answer"]


def test_custom_lab_from_3d_model(c):
    assert c.post("/api/labs", json={"code": "LAB-X", "name": "Nowe lab"}, headers=INTERN).status_code == 403
    lab = c.post("/api/labs", json={"code": "LAB-X", "name": "Laboratorium testowe", "building": "C"},
                 headers=ADMIN).json()
    assert lab["id"] == "lab-lab-x"
    glb = c.get("/api/labs/lab-204/export/model.glb").content
    manifest = b'[{"node": "FRZ-80", "id": "ULT-1", "name": "Zamrazarka testowa", "kind": "freezer"}]'
    r = c.post(f"/api/labs/{lab['id']}/model", headers=ADMIN,
               files={"file": ("lab.glb", glb, "model/gltf-binary"), "manifest": ("m.json", manifest, "application/json")})
    assert r.status_code == 200, r.text
    res = r.json()
    assert len(res["created"]) >= 12 and "ULT-1" in res["created"]
    detail = c.get(f"/api/labs/{lab['id']}").json()
    assert detail["glb_url"].startswith("/api/documents/") and detail["model_meta"]["nodes"]["FRZ-80"] == "ULT-1"
    assert 19 < detail["width"] < 21 and any(e["kind"] == "bench" for e in detail["equipment"])
    assert c.get(detail["glb_url"]).content[:4] == b"glTF"
    route = c.post("/api/route", json={"lab_id": lab["id"], "stops": ["ULT-1"]}, headers=ADMIN).json()
    assert route["order"] == ["ULT-1"] and route["distance_m"] > 0
    assert c.delete(f"/api/labs/{lab['id']}/model", headers=ADMIN).json()["ok"]


def test_optional_stubs_do_not_fail(c):
    for method, url in [("post", "/api/nfc/TAG1")]:
        r = getattr(c, method)(url)
        assert r.status_code == 200 and r.json()["enabled"] is False


def test_inspection_reminders(c):
    items = c.get("/api/notifications/inspections", params={"lab_id": "lab-204"}).json()
    assert items["enabled"] is True and items["items"]
    frz = [i for i in items["items"] if i["equipment_id"] == "FRZ-80" and i["kind"] == "certificate"]
    assert frz and 0 <= frz[0]["days_left"] <= 14 and frz[0]["title"].startswith("Certyfikat")
    en = c.get("/api/notifications/inspections", params={"lab_id": "lab-204"}, headers={"Accept-Language": "en"}).json()
    assert any(i["title"].startswith("Certificate") for i in en["items"])
    assert all(i["days_left"] <= 14 for i in items["items"])
    assert c.post("/api/notifications/inspections/run", params={"lab_id": "lab-204"}, headers=INTERN).status_code == 403
    first = c.post("/api/notifications/inspections/run", params={"lab_id": "lab-204"}, headers=LEADER).json()
    assert first["notifications"] > 0
    again = c.post("/api/notifications/inspections/run", params={"lab_id": "lab-204"}, headers=LEADER).json()
    assert again["notifications"] == 0 and again["skipped"] >= first["notifications"]
    resp = frz[0]["responsible_id"]
    notes = c.get("/api/notifications", params={"user_id": resp}).json()
    assert any(n["kind"] == "inspection" and n["ref_type"] == "equipment" and n["ref_id"] == "FRZ-80" for n in notes)
    piotr = c.get("/api/notifications", params={"user_id": "u-piotr"}).json()
    assert any(n["kind"] == "inspection" for n in piotr)
