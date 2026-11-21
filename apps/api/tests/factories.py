"""Inline test inputs (no data files in the repo)."""

from fastapi.testclient import TestClient

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def new_case(client: TestClient, name: str = "Testbouw B.V.", **company: object) -> dict:
    body = {
        "company": {"name": name, "legal_form": "bv", "sbi_code": "4322", **company},
        "loan_amount": "250000",
        "loan_purpose": "equipment",
        "loan_term_months": 60,
    }
    response = client.post("/api/cases", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, case_id: str, name: str, data: bytes, kind: str | None = None):
    form = {"kind": kind} if kind else {}
    return client.post(f"/api/cases/{case_id}/documents", files={"file": (name, data)}, data=form)
