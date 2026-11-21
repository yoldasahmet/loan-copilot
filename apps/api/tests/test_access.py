"""Advisor B must never see advisor A's cases or files: 404, not 403."""

from tests.factories import MINIMAL_PDF, new_case, upload


def test_advisor_cannot_see_other_advisors_case(login) -> None:
    a, b = login("advisor"), login("advisor")
    case = new_case(a, "Alfa Installatie B.V.")
    case_id = case["id"]

    assert b.get(f"/api/cases/{case_id}").status_code == 404
    assert b.patch(f"/api/cases/{case_id}", json={"notes": "x"}).status_code == 404
    assert b.delete(f"/api/cases/{case_id}").status_code == 404
    assert b.get(f"/api/cases/{case_id}/documents").status_code == 404
    assert upload(b, case_id, "report_2025.pdf", MINIMAL_PDF).status_code == 404
    assert b.get("/api/cases").json()["items"] == []
    assert a.get(f"/api/cases/{case_id}").status_code == 200


def test_advisor_cannot_fetch_other_advisors_files(login) -> None:
    a, b = login("advisor"), login("advisor")
    case_id = new_case(a)["id"]
    doc = upload(a, case_id, "annual_report_2025.pdf", MINIMAL_PDF).json()

    assert b.get(f"/api/documents/{doc['id']}/file").status_code == 404
    assert b.post(f"/api/documents/{doc['id']}/allow").status_code == 404
    assert b.delete(f"/api/documents/{doc['id']}").status_code == 404
    response = a.get(f"/api/documents/{doc['id']}/file")
    assert response.status_code == 200
    assert response.content == MINIMAL_PDF
    assert response.headers["content-disposition"].startswith("inline")


def test_admin_sees_all_cases(login) -> None:
    a, admin = login("advisor"), login("admin")
    case_id = new_case(a)["id"]
    assert admin.get(f"/api/cases/{case_id}").status_code == 200
    assert [c["id"] for c in admin.get("/api/cases").json()["items"]] == [case_id]


def test_list_search_and_status_filter(login) -> None:
    a = login("advisor")
    first = new_case(a, "Kesdra Bouw B.V.")
    new_case(a, "Morvik IT B.V.")
    a.patch(f"/api/cases/{first['id']}", json={"status": "waiting_review"})

    found = a.get("/api/cases", params={"q": "kesdra"}).json()
    assert [c["company"]["name"] for c in found["items"]] == ["Kesdra Bouw B.V."]
    waiting = a.get("/api/cases", params={"status": "waiting_review"}).json()
    assert len(waiting["items"]) == 1
    assert waiting["stats"]["open_cases"] == 2
    assert waiting["stats"]["waiting_review"] == 1


def test_only_admin_can_reassign(login) -> None:
    a, b, admin = login("advisor"), login("advisor"), login("admin")
    case_id = new_case(a)["id"]
    b_id = b.get("/api/auth/me").json()["id"]
    assert a.patch(f"/api/cases/{case_id}", json={"advisor_id": b_id}).status_code == 403
    assert admin.patch(f"/api/cases/{case_id}", json={"advisor_id": b_id}).status_code == 200
    assert b.get(f"/api/cases/{case_id}").status_code == 200
    assert a.get(f"/api/cases/{case_id}").status_code == 404
