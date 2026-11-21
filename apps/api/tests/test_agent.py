import uuid

from sqlalchemy import select

from loancopilot.db import SessionLocal
from loancopilot.memo import SECTIONS
from loancopilot.models import AiRun, Case, Document, Memo
from tests.factories import new_case
from tests.test_retrieval import TEXTS, _add_chunks


def add_report(case_id: str) -> None:
    """An indexed document with three text chunks (memo passages need a document). Kind
    "other" so the analysis step makes no extraction call."""
    with SessionLocal() as db:
        doc = Document(case_id=case_id, kind="other", filename="business_plan_2025.pdf",
                       sha256=uuid.uuid4().hex * 2, mime="application/pdf", size_bytes=1,
                       year=2025, status="indexed")  # fmt: skip
        db.add(doc)
        db.commit()
        doc_id = doc.id
    _add_chunks(case_id, TEXTS, doc_id)


def memo_text(extra: str = "") -> str:
    body = {s: f"Text for {s.lower()} [S1]." for s in SECTIONS}
    body["Loan request"] = "The company requests €250,000 over 60 months [S2]." + extra
    return "\n\n".join(f"## {s}\n{t}" for s, t in body.items())


def test_prepare_redrafts_waits_for_review_then_versions_and_approves(login, fake_llm) -> None:
    a = login("advisor")
    case_id = new_case(a, "Kesdra Installatie B.V.")["id"]
    add_report(case_id)
    fake_llm.queue(memo_text(" Revenue grew 17% [S1]."))  # 17% is in no source → redraft
    fake_llm.queue(memo_text())
    started = a.post(f"/api/cases/{case_id}/prepare")
    assert started.status_code == 202

    run = a.get(f"/api/cases/{case_id}/prepare").json()
    assert run["status"] == "waiting_review", run
    steps = {s["name"]: s for s in run["steps"]}
    assert [s["status"] for s in run["steps"]][:6] == ["done"] * 6
    assert steps["human_review"]["status"] == "waiting"
    assert "(redraft)" in steps["draft_memo"]["note"]
    redraft = fake_llm.requests[1].user
    assert "17%" in redraft and "Revenue grew" not in fake_llm.requests[0].system
    assert a.get(f"/api/cases/{case_id}").json()["status"] == "waiting_review"

    memo = a.get(f"/api/cases/{case_id}/memo").json()
    assert memo["version"] == 1 and memo["status"] == "draft"
    assert memo["verification"]["unverified"] == []
    assert [x["unverified"] for x in memo["verification"]["attempts"]] == [["17%"], []]
    assert memo["verification"]["missing_sections"] == []
    assert {s["type"] for s in memo["sources"]} >= {"document", "metric"}
    first = memo["sources"][0]
    assert first["id"] == "S1" and first["type"] == "document" and first["page_from"] == 5
    assert "[S1]" in memo["content_md"]

    fake_llm.queue(memo_text(" Shorter, as requested."))
    note = {"note": "Make the loan request section shorter."}
    assert a.post(f"/api/cases/{case_id}/memo/request-changes", json=note).status_code == 202
    memo2 = a.get(f"/api/cases/{case_id}/memo").json()
    assert memo2["version"] == 2 and "Shorter" in memo2["content_md"]
    assert "Make the loan request section shorter." in fake_llm.requests[-1].user
    assert a.get(f"/api/cases/{case_id}/memo?version=1").json()["status"] == "changes_requested"
    assert [v["version"] for v in memo2["versions"]] == [1, 2]

    assert a.post(f"/api/cases/{case_id}/memo/approve").status_code == 202
    assert a.get(f"/api/cases/{case_id}/prepare").json()["status"] == "done"
    approved = a.get(f"/api/cases/{case_id}/memo").json()
    assert approved["status"] == "approved" and approved["approved_by"]
    assert a.get(f"/api/cases/{case_id}").json()["status"] == "ready"
    assert a.post(f"/api/cases/{case_id}/memo/approve").status_code == 409


def test_audit_log_lists_every_llm_call(login, fake_llm) -> None:
    a, admin = login("advisor"), login("admin")
    case_id = new_case(a)["id"]
    add_report(case_id)
    fake_llm.queue(memo_text())
    a.post(f"/api/cases/{case_id}/prepare")
    rows = admin.get("/api/admin/audit").json()
    assert [r["kind"] for r in rows] == ["memo"]
    row = rows[0]
    assert row["input_tokens"] == 120 and row["latency_ms"] >= 0 and row["case_label"]
    detail = admin.get(f"/api/admin/audit/{row['id']}").json()
    assert detail["output_text"].startswith("## Summary")
    assert a.get("/api/admin/audit").status_code == 403
    assert admin.get("/api/admin/audit", params={"kind": "chat"}).json() == []


def test_deleting_a_case_erases_memos_checkpoints_and_ai_output(login, fake_llm) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    add_report(case_id)
    fake_llm.queue(memo_text())
    a.post(f"/api/cases/{case_id}/prepare")
    assert a.delete(f"/api/cases/{case_id}").status_code == 204
    with SessionLocal() as db:
        assert db.get(Case, uuid.UUID(case_id)) is None
        assert db.scalars(select(Memo)).all() == []
        run = db.scalar(select(AiRun))
        assert run.output_text is None and run.case_id is None and run.input_tokens == 120
        count = db.execute(select(AiRun.id)).all()
        assert len(count) == 1
        from sqlalchemy import text

        left = db.execute(text("SELECT count(*) FROM checkpoints WHERE thread_id LIKE :t"),
                          {"t": f"{case_id}:%"}).scalar()  # fmt: skip
        assert left == 0
