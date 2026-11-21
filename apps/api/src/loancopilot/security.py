"""Upload checks. (Pseudonymisation and the injection scan are added in later milestones.)"""

from pathlib import PurePath

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MIME = {"pdf": "application/pdf", "xml": "application/xml", "csv": "text/csv"}


class UploadRejected(ValueError):
    pass


def _looks_like_csv(data: bytes) -> bool:
    try:
        text = data[:4096].decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    first = text.splitlines()[0] if text else ""
    return "\x00" not in text and ("," in first or ";" in first)


def check_upload(filename: str, data: bytes) -> str:
    """Validate extension, size and magic bytes. Returns the normalised extension."""
    ext = PurePath(filename).suffix.lower().lstrip(".")
    if ext not in MIME:
        raise UploadRejected("Only PDF, XML and CSV files are allowed.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("Files may be at most 20 MB.")
    if not data:
        raise UploadRejected("The file is empty.")
    head = data[:64].lstrip(b"\xef\xbb\xbf \t\r\n")
    valid = {
        "pdf": data.startswith(b"%PDF-"),
        "xml": head.startswith(b"<?xml") or head.startswith(b"<"),
        "csv": not head.startswith((b"%PDF", b"<")) and _looks_like_csv(data),
    }[ext]
    if not valid:
        raise UploadRejected(f"The file content does not match the .{ext} extension.")
    return ext
