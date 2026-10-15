"""
CEREBRO deterministic text segmentation.

Creates source-addressable segments while preserving exact
character offsets into the original artifact.

No AI.
No embeddings.
No semantic enrichment.
"""

import re


def segment_sentences(source_text: str):
    """
    Deterministically segment text into sentences while retaining
    exact source character offsets.
    """

    segments = []

    pattern = re.compile(
        r'[^.!?]+(?:[.!?]+|$)',
        re.MULTILINE
    )

    for match in pattern.finditer(source_text):

        raw_text = match.group(0)

        leading = len(raw_text) - len(raw_text.lstrip())
        trailing_text = raw_text.strip()

        if not trailing_text:
            continue

        start_char = match.start() + leading
        end_char = start_char + len(trailing_text)

        segments.append({
            "text": trailing_text,
            "source_location": {
                "type": "character_range",
                "start_char": start_char,
                "end_char": end_char,
            },
        })

    return segments
