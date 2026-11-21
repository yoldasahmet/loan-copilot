import os
from pathlib import Path

from tests.factories import MINIMAL_PDF, new_case, upload

CSV = (
    b"date,amount,counterparty_name,counterparty_iban,description,balance\n"
    b"2026-01-02,100.00,A,,x,100\n"
)
XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<Document></Document>\n'


def test_upload_stores_file_and_infers_kind_and_year(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    doc = upload(a, case_id, "annual_report_2025.pdf", MINIMAL_PDF).json()
    assert doc["kind"] == "annual_report" and doc["year"] == 2025 and doc["status"] == "uploaded"
    stored = list(Path(os.environ["DATA_DIR"], "files", case_id).iterdir())
    assert [p.suffix for p in stored] == [".pdf"]

    statement = upload(a, case_id, "statements.xml", XML).json()
    assert statement["kind"] == "bank_statement"
    assert upload(a, case_id, "statements.csv", CSV).status_code == 201
    assert len(a.get(f"/api/cases/{case_id}/documents").json()) == 3


def test_same_file_twice_is_a_noop(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    first = upload(a, case_id, "report.pdf", MINIMAL_PDF).json()
    second = upload(a, case_id, "copy-of-report.pdf", MINIMAL_PDF).json()
    assert first["id"] == second["id"]
    assert len(a.get(f"/api/cases/{case_id}/documents").json()) == 1


def test_rejects_wrong_extension_magic_bytes_and_size(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    assert upload(a, case_id, "notes.docx", b"PK\x03\x04").status_code == 422
    assert upload(a, case_id, "fake.pdf", b"MZ\x90\x00 not a pdf").status_code == 422
    assert upload(a, case_id, "fake.xml", MINIMAL_PDF).status_code == 422
    assert upload(a, case_id, "fake.csv", b"\x00\x01\x02binary").status_code == 422
    too_big = MINIMAL_PDF + b"0" * (20 * 1024 * 1024)
    response = upload(a, case_id, "big.pdf", too_big)
    assert response.status_code in (413, 422)
    assert a.get(f"/api/cases/{case_id}/documents").json() == []


def test_delete_case_erases_files_and_rows(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    upload(a, case_id, "report.pdf", MINIMAL_PDF)
    assert a.delete(f"/api/cases/{case_id}").status_code == 204
    assert a.get(f"/api/cases/{case_id}").status_code == 404
    assert not Path(os.environ["DATA_DIR"], "files", case_id).exists()
