from loancopilot.security import Pseudonymiser


def make() -> Pseudonymiser:
    return Pseudonymiser("Laumond Installatietechniek B.V.", ["Fenne Ketting"],
                         ["Tikpin Acquiring", "Kesdra Bouw B.V."])  # fmt: skip


def test_mask_and_restore_names_ibans_emails_phones() -> None:
    p = make()
    text = ("Laumond Installatietechniek (contact Fenne Ketting, fenne.ketting@example.com, "
            "06 1234 5678) received €12,000 from Kesdra Bouw B.V. on NL91 DEMO 0417 1643 00 "
            "and NL91DEMO0417164300.")  # fmt: skip
    masked = p.mask(text)
    for secret in ("Laumond", "Fenne", "example.com", "5678", "Kesdra", "0417"):
        assert secret not in masked
    assert "[COMPANY]" in masked and "[PERSON_1]" in masked and "[COUNTERPARTY_2]" in masked
    assert masked.count("[IBAN_1]") == 2  # same IBAN, same placeholder
    assert "€12,000" in masked  # amounts are not phone numbers
    assert p.unmask("[COMPANY] pays [COUNTERPARTY_2]") == (
        "Laumond Installatietechniek B.V. pays Kesdra Bouw B.V.")  # fmt: skip
    assert "fenne.ketting@example.com" in p.unmask(masked)


def test_restore_placeholder_split_across_stream_chunks() -> None:
    p = make()
    p.mask("Fenne Ketting")
    chunks = ["The owner [PER", "SON_1] works for [COM", "PANY", "]. Price is [", "unknown"]
    out = "".join(p.unmask_stream(chunks))
    assert (
        out
        == "The owner Fenne Ketting works for Laumond Installatietechniek B.V.. Price is [unknown"
    )


def test_unknown_placeholders_are_left_alone() -> None:
    assert make().unmask("See [S3] and [COUNTERPARTY_99]") == "See [S3] and [COUNTERPARTY_99]"
