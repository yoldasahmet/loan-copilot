import uuid

from sqlalchemy import select

from loancopilot.db import SessionLocal
from loancopilot.embeddings import embed
from loancopilot.history import import_jsonl
from loancopilot.models import Analysis, Chunk, Lender
from tests.factories import MINIMAL_PDF, new_case
from tests.test_history import LINE, jsonl, line, make_lender


def _seed_history() -> None:
    make_lender()
    rows = []
    for m in range(1, 8):  # 5 approved, 2 declined by Testbank
        decision = {**LINE["decisions"][0], "decided_on": f"2024-0{m}-20",
                    "decision": "approved" if m % 3 else "declined"}  # fmt: skip
        rows.append(line(application__applied_on=f"2024-0{m}-01", decisions=[decision]))
    with SessionLocal() as db:
        assert import_jsonl(db, jsonl(*rows))["imported"] == 7


def test_similar_cases_with_reasons_and_decisions(login) -> None:
    _seed_history()
    a = login("advisor")
    case_id = new_case(a, "Kesdra Installatie B.V.", founded_year=2012)["id"]
    a.post(f"/api/cases/{case_id}/analysis/run")
    similar = a.get(f"/api/cases/{case_id}/similar").json()
    assert len(similar) == 5
    first = similar[0]
    assert first["ref"].startswith("H-") and first["decisions"][0]["lender"] == "Testbank"
    assert "Same sector" in first["reasons"] and "Same loan purpose" in first["reasons"]
    with SessionLocal() as db:  # cached on the analysis row
        assert db.get(Analysis, uuid.UUID(case_id)).similar is not None


def test_lender_matches_with_checks_precedents_and_cited_summary(login, fake_llm) -> None:
    _seed_history()
    make_lender("Smallbank", max_amount=200_000)
    with SessionLocal() as db:  # one criteria passage for Testbank
        testbank = db.scalar(select(Lender).where(Lender.name == "Testbank"))
        text = "We finance equipment for established construction companies."
        db.add(Chunk(lender_id=testbank.id, kind="text", text=text, context_header="Testbank",
                     embedding=embed([text])[0]))  # fmt: skip
        db.commit()
    a = login("advisor")
    case_id = new_case(a, "Kesdra Installatie B.V.", founded_year=2012)["id"]
    a.post(f"/api/cases/{case_id}/analysis/run")
    fake_llm.queue({"summaries": [
        {"lender": "Testbank", "summary": "Testbank finances equipment for construction [S1]."},
        {"lender": "Smallbank", "summary": "The requested amount is above Smallbank's maximum."},
    ]})  # fmt: skip
    result = a.get(f"/api/cases/{case_id}/lenders").json()
    names = [lender["name"] for lender in result["lenders"]]
    assert names == ["Testbank", "Smallbank"]  # failing a hard check sorts last
    testbank = result["lenders"][0]
    assert testbank["precedents"]["decided"] == 7 and testbank["precedents"]["approved"] == 5
    assert testbank["source_ids"] == ["S1"] and "[S1]" in testbank["summary"]
    assert result["sources"][0]["id"] == "S1"
    small = result["lenders"][1]
    assert not small["passes_hard_checks"]
    assert next(c for c in small["checks"] if c["check"] == "Loan amount")["passed"] is False
    assert "score" not in str(result).lower()
    again = a.get(f"/api/cases/{case_id}/lenders").json()  # served from cache: no second call
    assert again["lenders"][0]["summary"] == testbank["summary"]
    assert len(fake_llm.requests) == 1


def test_matching_endpoints_respect_case_access(login) -> None:
    a, b = login("advisor"), login("advisor")
    case_id = new_case(a)["id"]
    assert b.get(f"/api/cases/{case_id}/similar").status_code == 404
    assert b.get(f"/api/cases/{case_id}/lenders").status_code == 404


def test_admin_lenders_and_history_import(login) -> None:
    advisor, admin = login("advisor"), login("admin")
    body = {"name": "Testbank", "product_type": "term_loan", "min_amount": 100000,
            "max_amount": 2000000, "min_revenue": 1000000, "min_years_trading": 3,
            "excluded_sector_groups": ["hospitality"], "allowed_legal_forms": ["bv"],
            "typical_rate_min": 0.055, "typical_rate_max": 0.085}  # fmt: skip
    assert advisor.post("/api/admin/lenders", json=body).status_code == 403
    created = admin.post("/api/admin/lenders", json=body)
    assert created.status_code == 201
    lender_id = created.json()["id"]
    assert admin.post("/api/admin/lenders", json=body).status_code == 409
    assert admin.patch(f"/api/admin/lenders/{lender_id}", json={"active": False}).json()[
        "active"] is False  # fmt: skip
    assert len(advisor.get("/api/admin/lenders").json()) == 1  # readable by every user
    up = admin.post(f"/api/admin/lenders/{lender_id}/documents",
                    files={"file": ("criteria.pdf", MINIMAL_PDF)})  # fmt: skip
    assert up.status_code == 201 and up.json()["kind"] == "lender_criteria"

    files = {"file": ("history.jsonl", jsonl(line(), "{broken").encode())}
    assert advisor.post("/api/admin/history/import", files=files).status_code == 403
    result = admin.post("/api/admin/history/import", files=files).json()
    assert result["imported"] == 1 and result["errors"][0]["line"] == 2
    assert admin.delete(f"/api/admin/lenders/{lender_id}").status_code == 204
