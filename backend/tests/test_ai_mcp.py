from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, User
from app.main import app
from app.services import ai


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def rpc(c, method, params=None, id_=1, **kw):
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        body["id"] = id_
    return c.post("/mcp", json=body, **kw)


class FakeClaude:
    """Scripted stand-in for anthropic.Anthropic: replays tool calls, then a final answer."""

    def __init__(self, steps):
        self.steps, self.requests = list(steps), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        kind, payload = self.steps.pop(0)
        if kind == "tools":
            content = [SimpleNamespace(type="tool_use", id=f"tu_{i}", name=n, input=a) for i, (n, a) in enumerate(payload)]
            return SimpleNamespace(stop_reason="tool_use", content=content, model="claude-opus-5-5")
        if kind == "refusal":
            return SimpleNamespace(stop_reason="refusal", content=[], model="claude-opus-5-5")
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=payload)],
                               model="claude-opus-5-5")


def test_ai_falls_back_to_keyword_assistant_without_credentials(c, monkeypatch):
    monkeypatch.setattr(ai.config, "AI_ENABLED", "auto")
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(ai.config, "ANTHROPIC_AUTH_TOKEN", None)
    assert c.get("/api/assistant/status").json()["enabled"] is False
    r = c.post("/api/assistant/ai", json={"lab_id": "lab-204", "question": "gdzie jest acetonitryl?"}).json()
    assert r["enabled"] is False and r["fallback"] == "keyword" and r["highlight"] == "CAB-F"


def test_ai_tool_loop_answers_with_lab_data(c):
    fake = FakeClaude([
        ("tools", [("search_documents", {"query": "wahania ciśnienia odpowietrz pompę"}), ("get_equipment", {"equipment_id": "HPLC-04"})]),
        ("tools", [("get_equipment", {"equipment_id": "NOPE-1"})]),
        ("text", "Odpowietrz pompę HPLC-04 przez 5 minut (instrukcja HPLC-04). Michał zna to urządzenie."),
    ])
    with SessionLocal() as db:
        user = db.get(User, "u-tomek")
        r = ai.ask(db, "lab-204", "Co zrobić z wahaniami ciśnienia?", user, "pl",
                   history=[{"role": "assistant", "content": "skipped: history must start with user"},
                            {"role": "user", "content": "Cześć"}, {"role": "assistant", "content": "Hej!"}],
                   client=fake)
    assert r["enabled"] and r["highlight"] == "HPLC-04"
    assert r["tools"] == ["search_documents", "get_equipment", "get_equipment"]
    assert any("HPLC-04" in d["title"] for d in r["documents"])
    first = fake.requests[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"find_in_lab", "search_documents", "list_quests"}
    msgs = fake.requests[0]["messages"]
    assert msgs[0] == {"role": "user", "content": "Cześć"} and "Tomek Lewandowski" in msgs[-1]["content"]
    # Tool results go back in one user message; the unknown device comes back as an error result.
    second = fake.requests[1]["messages"][-1]["content"]
    assert len(second) == 2 and '"status"' in second[1]["content"]
    err = fake.requests[2]["messages"][-1]["content"][0]
    assert err["is_error"] and "NOPE-1" in err["content"]


def test_ai_refusal_and_api_error(c):
    import anthropic

    with SessionLocal() as db:
        r = ai.ask(db, "lab-204", "?", None, "en", client=FakeClaude([("refusal", None)]))
        assert r["enabled"] and "can't help" in r["answer"]

        class Broken(FakeClaude):
            def create(self, **kw):
                raise anthropic.APIConnectionError(request=None)

        assert ai.ask(db, "lab-204", "?", None, "en", client=Broken([])) is None


def test_mcp_handshake_and_tools(c):
    init = rpc(c, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "test", "version": "1"}}).json()
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "smartlab" and "tools" in init["result"]["capabilities"]
    assert rpc(c, "notifications/initialized", id_=None).status_code == 202
    assert rpc(c, "ping").json()["result"] == {}
    tools = rpc(c, "tools/list").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"list_labs", "find_in_lab", "get_equipment", "search_documents", "list_quests"} <= names
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    assert c.get("/api/mcp/tools").json()["enabled"] is True
    assert c.get("/mcp").status_code == 405


def test_mcp_tool_calls(c):
    labs = rpc(c, "tools/call", {"name": "list_labs", "arguments": {}}).json()["result"]
    assert "lab-204" in labs["content"][0]["text"]
    r = rpc(c, "tools/call", {"name": "get_equipment", "arguments": {"lab_id": "lab-204", "equipment_id": "HPLC-04"}}).json()
    assert r["result"]["isError"] is False and "Chromatograf HPLC-04" in r["result"]["content"][0]["text"]
    r = rpc(c, "tools/call", {"name": "find_in_lab", "arguments": {"query": "acetonitryl"}}).json()
    assert "CAB-F" in r["result"]["content"][0]["text"]
    r = rpc(c, "tools/call", {"name": "list_quests", "arguments": {"user_id": "u-tomek"}}).json()
    assert '"mine"' in r["result"]["content"][0]["text"]
    r = rpc(c, "tools/call", {"name": "list_quests", "arguments": {}}).json()
    assert r["result"]["isError"] is True
    r = rpc(c, "tools/call", {"name": "get_equipment", "arguments": {"lab_id": "lab-102", "equipment_id": "HPLC-04"}}).json()
    assert r["result"]["isError"] is True
    assert rpc(c, "tools/call", {"name": "drop_tables"}).json()["error"]["code"] == -32602
    assert rpc(c, "resources/list").json()["error"]["code"] == -32601
    batch = c.post("/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                 {"jsonrpc": "2.0", "method": "notifications/initialized"}]).json()
    assert batch == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


def test_mcp_rejects_foreign_browser_origin(c):
    assert rpc(c, "ping", headers={"Origin": "https://evil.example"}).status_code == 403
    assert rpc(c, "ping", headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert c.post("/mcp", content=b"{not json", headers={"Content-Type": "application/json"}).status_code == 400
