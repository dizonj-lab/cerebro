"""
CEREBRO deterministic artifact inspection.

This module identifies and validates an artifact using deterministic
evidence before AI processing.

No AI inference.
No artifact registration.
No knowledge construction.
"""

from datetime import datetime, timezone
import hashlib
import mimetypes


def detect_file_signature(content: bytes):
    """
    Identify common artifact types using byte signatures.

    Filename and extension are not trusted as authoritative evidence.
    """

    signatures = [
        (b"%PDF-", "application/pdf", "pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png", "image"),
        (b"\xff\xd8\xff", "image/jpeg", "image"),
        (b"GIF87a", "image/gif", "image"),
        (b"GIF89a", "image/gif", "image"),
        (b"RIFF", "riff-container", "container"),
        (b"ID3", "audio/mpeg", "audio"),
        (b"PK\x03\x04", "zip-container", "container"),
    ]

    for signature, detected_type, modality in signatures:
        if content.startswith(signature):
            return detected_type, modality

    return None, None


def validate_text_content(content: bytes):
    """
    Determine whether raw bytes represent plausible UTF-8 text.
    """

    result = {
        "is_utf8": False,
        "is_text": False,
        "printable_ratio": 0.0,
        "null_bytes": 0,
        "decoded_text": None,
        "reason": None,
    }

    result["null_bytes"] = content.count(b"\x00")

    try:
        decoded = content.decode("utf-8")
        result["is_utf8"] = True
        result["decoded_text"] = decoded

    except UnicodeDecodeError:
        result["reason"] = "Content is not valid UTF-8."
        return result

    if not decoded:
        result["reason"] = "Artifact contains no text."
        return result

    printable_count = sum(
        1
        for char in decoded
        if char.isprintable() or char in "\n\r\t"
    )

    result["printable_ratio"] = (
        printable_count / len(decoded)
    )

    result["is_text"] = (
        result["is_utf8"]
        and result["null_bytes"] == 0
        and result["printable_ratio"] >= 0.95
    )

    if result["is_text"]:
        result["reason"] = (
            "Valid UTF-8 with high printable-text ratio."
        )
    else:
        result["reason"] = (
            "Content does not satisfy text validation rules."
        )

    return result


def expected_modality_from_filename(name: str):
    """
    Return advisory modality based on extension.
    """

    extension = (
        name.lower().rsplit(".", 1)[-1]
        if "." in name
        else ""
    )

    mapping = {
        "txt": "text",
        "pdf": "pdf",

        "png": "image",
        "jpg": "image",
        "jpeg": "image",
        "gif": "image",

        "wav": "audio",
        "mp3": "audio",

        "mp4": "video",

        "pptx": "office",
        "docx": "office",
    }

    return mapping.get(extension, "unknown")


def validate_filename_consistency(
    name: str,
    detected_modality: str
):
    """
    Compare advisory filename modality with content-derived modality.
    """

    declared_modality = expected_modality_from_filename(name)

    if declared_modality == "unknown":
        status = "UNVERIFIED"

    elif detected_modality == "unknown":
        status = "UNVERIFIED"

    elif declared_modality == detected_modality:
        status = "MATCH"

    else:
        status = "MISMATCH"

    return {
        "filename": name,
        "declared_modality": declared_modality,
        "detected_modality": detected_modality,
        "status": status,
    }


def inspect_artifact(
    filename: str,
    content: bytes
):
    """
    Perform deterministic CEREBRO artifact inspection.

    Input:
        filename
        raw artifact bytes

    Output:
        deterministic inspection contract
    """

    extension_mime, _ = mimetypes.guess_type(filename)

    signature_type, signature_modality = (
        detect_file_signature(content)
    )

    text_validation = validate_text_content(content)

    if signature_modality:
        detected_modality = signature_modality

    elif text_validation["is_text"]:
        detected_modality = "text"

    else:
        detected_modality = "unknown"

    consistency = validate_filename_consistency(
        filename,
        detected_modality
    )

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
            "filename_consistency": consistency["status"],
        },

        "content_validation": {
            "is_utf8": text_validation["is_utf8"],
            "is_text": text_validation["is_text"],
            "printable_ratio": text_validation["printable_ratio"],
            "null_bytes": text_validation["null_bytes"],
            "reason": text_validation["reason"],
        },

        "provenance": {
            "method": "deterministic_artifact_inspection",
            "ai_used": False,
            "human_confirmed": False,
            "inspected_at": datetime.now(
                timezone.utc
            ).isoformat(),
        },

        "status": "INSPECTED",
    }
