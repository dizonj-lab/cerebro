"""Plain text and Markdown."""
from app.services.artifacts.extraction.base import (
    Block,
    ExtractionFailed,
    ExtractionResult,
    SourceLocation,
)


class PlainTextAdapter:
    modality = "text"
    signature_modalities = ("text",)
    extensions = (".txt", ".md", ".markdown")

    def extract(self, content: bytes, *, filename: str) -> ExtractionResult:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExtractionFailed("File is not valid UTF-8 text.") from exc

        blocks: list[Block] = []
        offset = 0
        # Blank lines delimit paragraphs; offsets stay true to the original.
        for index, raw in enumerate(text.split("\n\n")):
            stripped = raw.strip()
            if stripped:
                start = text.index(stripped, offset)
                blocks.append(
                    Block(
                        text=stripped,
                        kind="heading" if stripped.startswith("#") else "paragraph",
                        location=SourceLocation(
                            paragraph=index + 1,
                            char_start=start,
                            char_end=start + len(stripped),
                        ),
                    )
                )
                offset = start + len(stripped)

        return ExtractionResult(
            blocks=blocks,
            structure={"paragraphs": len(blocks), "lines": len(text.splitlines())},
        )
