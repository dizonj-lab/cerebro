"""PDF text extraction, page by page.

Text layer only. A scanned PDF yields no text and is reported as such rather
than silently producing an empty artifact; OCR is a later phase.
"""
import io

from app.services.artifacts.extraction import properties as doc_properties
from app.services.artifacts.extraction.base import (
    Block,
    ExtractionFailed,
    ExtractionResult,
    SourceLocation,
)


class PdfAdapter:
    modality = "pdf"
    signature_modalities = ("pdf",)
    extensions = (".pdf",)

    def extract(self, content: bytes, *, filename: str) -> ExtractionResult:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(content))
        except (PdfReadError, OSError, ValueError) as exc:
            raise ExtractionFailed(f"Could not read the PDF: {exc}") from exc

        if reader.is_encrypted:
            raise ExtractionFailed("The PDF is encrypted and cannot be read.")

        blocks: list[Block] = []
        errors: list[str] = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001 - one bad page must not lose the rest
                errors.append(f"Page {page_number}: {exc}")
                continue

            offset = 0
            for raw in page_text.split("\n\n"):
                stripped = raw.strip()
                if not stripped:
                    continue
                start = page_text.index(stripped, offset)
                blocks.append(
                    Block(
                        text=stripped,
                        kind="paragraph",
                        location=SourceLocation(
                            page=page_number,
                            char_start=start,
                            char_end=start + len(stripped),
                        ),
                    )
                )
                offset = start + len(stripped)

        if not blocks:
            raise ExtractionFailed(
                "No text layer found. This looks like a scanned PDF; OCR arrives in a "
                "later phase."
            )

        return ExtractionResult(
            blocks=blocks,
            structure={"pages": len(reader.pages), "blocks": len(blocks)},
            properties=doc_properties.from_pdf(reader),
            errors=errors,
        )
