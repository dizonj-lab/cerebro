"""
CEREBRO AI metadata enrichment capability.

AI output is suggestive only.

It does NOT:
- confirm metadata,
- register artifacts,
- create trusted knowledge.
"""

import json


ENRICHMENT_FIELDS = [
    "title",
    "author",
    "created_date",
    "language",
    "description",
    "topics",
    "people",
    "organizations",
    "projects",
    "tags",
]


def build_metadata_enrichment_prompt(
    extracted_artifact: dict,
    metadata_result: dict,
):
    """
    Build a grounded metadata-enrichment request.
    """

    source_text = (
        extracted_artifact["representation"]["content"]
    )

    existing_metadata = (
        metadata_result["extracted_metadata"]
    )

    schema = {
        "title": None,
        "author": None,
        "created_date": None,
        "language": None,
        "description": None,
        "topics": [],
        "people": [],
        "organizations": [],
        "projects": [],
        "tags": [],
    }

    return f"""
You are performing metadata enrichment for CEREBRO.

Use ONLY the supplied artifact content as evidence.

Do not invent information.

If an author, date, person, organization, project or other
fact cannot be established from the artifact, return null
or an empty list.

Return valid JSON only.

Required schema:

{json.dumps(schema, indent=2)}

Existing deterministic metadata:

{json.dumps(existing_metadata, indent=2)}

ARTIFACT CONTENT:

--- BEGIN ARTIFACT ---
{source_text}
--- END ARTIFACT ---
""".strip()


def build_ai_prefill(
    ai_result: dict,
):
    """
    Convert model output into CEREBRO field-level suggestions.

    AI values remain unconfirmed.
    """

    response = ai_result["response"]

    fields = {}

    for field_name in ENRICHMENT_FIELDS:

        value = response.get(field_name)

        fields[field_name] = {
            "value": value,
            "source": "ai_suggested",
            "method": "ai_metadata_enrichment",
            "model": ai_result["model"],
            "provider": ai_result["provider"],
            "status": "suggested",
            "user_confirmed": False,
        }

    return fields
