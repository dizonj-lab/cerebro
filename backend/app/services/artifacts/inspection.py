"""Deterministic artifact inspection.

Identifies and validates an artifact from its bytes, before any AI touches
it. Ported from poc/src/inspection.py (EXP-INGEST-001/002).

No AI inference. No registration. No knowledge construction.
"""
import hashlib
import mimetypes
from datetime import UTC, datetime

# Byte signatures. The filename is advisory; bytes are the evidence.
_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "image"),
    (b"\xff\xd8\xff", "image/jpeg", "image"),
    (b"GIF87a", "image/gif", "image"),
    (b"GIF89a", "image/gif", "image"),
    (b"RIFF", "riff-container", "container"),
    (b"ID3", "audio/mpeg", "audio"),
    (b"PK\x03\x04", "zip-container", "container"),
)

_EXTENSION_MODALITY = {
    "txt": "text", "md": "text", "pdf": "pdf",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "wav": "audio", "mp3": "audio", "mp4": "video",
    "pptx": "office", "docx": "office",
}

# A text artifact must be valid UTF-8, free of NULs, and overwhelmingly
# printable. Below this ratio it is treated as binary.
_PRINTABLE_THRESHOLD = 0.95


def detect_file_signature(content: bytes) -> tuple[str | None, str | None]:
    for signature, detected_type, modality in _SIGNATURES:
        if content.startswith(signature):
            return detected_type, modality
    return None, None


def validate_text_content(content: bytes) -> dict:
    """Decide whether raw bytes are plausible UTF-8 text."""
    result = {
        "is_utf8": False, "is_text": False, "printable_ratio": 0.0,
        "null_bytes": content.count(b"\x00"), "decoded_text": None, "reason": None,
    }

    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        result["reason"] = "Content is not valid UTF-8."
        return result

    result["is_utf8"] = True
    result["decoded_text"] = decoded

    if not decoded:
        result["reason"] = "Artifact contains no text."
        return result

    printable = sum(1 for c in decoded if c.isprintable() or c in "\n\r\t")
    result["printable_ratio"] = printable / len(decoded)
    result["is_text"] = (
        result["null_bytes"] == 0 and result["printable_ratio"] >= _PRINTABLE_THRESHOLD
    )
    result["reason"] = (
        "Valid UTF-8 with high printable-text ratio."
        if result["is_text"]
        else "Content does not satisfy text validation rules."
    )
    return result


def expected_modality_from_filename(name: str) -> str:
    extension = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    return _EXTENSION_MODALITY.get(extension, "unknown")


def validate_filename_consistency(name: str, detected_modality: str) -> str:
    """Compare what the filename claims against what the bytes show."""
    declared = expected_modality_from_filename(name)
    if declared == "unknown" or detected_modality == "unknown":
        return "UNVERIFIED"
    return "MATCH" if declared == detected_modality else "MISMATCH"


def inspect_artifact(filename: str, content: bytes) -> dict:
    """Return the deterministic inspection contract for an artifact."""
    extension_mime, _ = mimetypes.guess_type(filename)
    signature_type, signature_modality = detect_file_signature(content)
    text = validate_text_content(content)

    if signature_modality:
        detected_modality = signature_modality
    elif text["is_text"]:
        detected_modality = "text"
    else:
        detected_modality = "unknown"

    return {
        "filename": filename,
        "file": {
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        "identification": {
            "extension_mime_guess": extension_mime,
            "signature_type": signature_type,
            "detected_modality": detected_modality,
            "filename_consistency": validate_filename_consistency(
                filename, detected_modality
            ),
        },
        "content_validation": {
            "is_utf8": text["is_utf8"],
            "is_text": text["is_text"],
            "printable_ratio": text["printable_ratio"],
            "null_bytes": text["null_bytes"],
            "reason": text["reason"],
        },
        "provenance": {
            "method": "deterministic_artifact_inspection",
            "ai_used": False,
            "human_confirmed": False,
            "inspected_at": datetime.now(UTC).isoformat(),
        },
        "status": "INSPECTED",
    }
