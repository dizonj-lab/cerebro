"""
CEREBRO evaluation capabilities.

Evaluates derived outputs before they cross trust boundaries.

This module does not:
- approve AI suggestions,
- register artifacts,
- create trusted knowledge,
- invoke models.
"""


REQUIRED_ENRICHMENT_FIELDS = {
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
}


def validate_enrichment_structure(ai_prefill: dict):
    """
    Validate structural integrity of CEREBRO AI metadata suggestions.
    """

    if not isinstance(ai_prefill, dict):
        return False

    if not REQUIRED_ENRICHMENT_FIELDS.issubset(
        ai_prefill.keys()
    ):
        return False

    for field_name in REQUIRED_ENRICHMENT_FIELDS:

        field = ai_prefill.get(field_name)

        if not isinstance(field, dict):
            return False

        if field.get("source") != "ai_suggested":
            return False

        if field.get("status") != "suggested":
            return False

        if field.get("user_confirmed") is not False:
            return False

    return True


def validate_required_fields(ai_prefill: dict):
    """
    Required fields means required contract fields are present.

    It does NOT mean every field must contain a value.
    Unknown values are valid.
    """

    return REQUIRED_ENRICHMENT_FIELDS.issubset(
        ai_prefill.keys()
    )


def detect_unsupported_claims(
    ai_prefill: dict,
    source_text: str,
):
    """
    Conservative deterministic grounding check.

    Checks explicit entity-like list values against source text.

    This is intentionally limited and is NOT a complete
    semantic hallucination detector.
    """

    source_lower = source_text.lower()

    evidence_fields = [
        "people",
        "organizations",
        "projects",
    ]

    unsupported = []

    for field_name in evidence_fields:

        field = ai_prefill.get(field_name, {})
        values = field.get("value")

        if values is None:
            continue

        if not isinstance(values, list):
            values = [values]

        for value in values:

            if not isinstance(value, str):
                continue

            candidate = value.strip()

            if (
                candidate
                and candidate.lower() not in source_lower
            ):
                unsupported.append({
                    "field": field_name,
                    "value": candidate,
                })

    return unsupported


def validate_entity_preservation(
    ai_prefill: dict,
    source_text: str,
):
    """
    Validate that suggested explicit entities can be traced
    to source text.

    This is a deterministic PoC gate, not semantic NER scoring.
    """

    unsupported = detect_unsupported_claims(
        ai_prefill,
        source_text
    )

    return len(unsupported) == 0


def evaluate_ai_enrichment(
    ai_prefill: dict,
    source_text: str,
):
    """
    Produce the validation gates expected by the CEREBRO Router.
    """

    structured_output_valid = (
        validate_enrichment_structure(ai_prefill)
    )

    required_fields_present = (
        validate_required_fields(ai_prefill)
    )

    unsupported_claims = (
        detect_unsupported_claims(
            ai_prefill,
            source_text
        )
    )

    unsupported_claims_detected = (
        len(unsupported_claims) > 0
    )

    entity_preservation_passed = (
        validate_entity_preservation(
            ai_prefill,
            source_text
        )
    )

    # Current deterministic grounding gate.
    # Deliberately conservative for the PoC.
    grounding_passed = (
        structured_output_valid
        and not unsupported_claims_detected
    )

    gates = {
        "structured_output_valid":
            structured_output_valid,

        "grounding_passed":
            grounding_passed,

        "required_fields_present":
            required_fields_present,

        "unsupported_claims_detected":
            unsupported_claims_detected,

        "entity_preservation_passed":
            entity_preservation_passed,
    }

    passed = (
        structured_output_valid
        and grounding_passed
        and required_fields_present
        and not unsupported_claims_detected
        and entity_preservation_passed
    )

    return {
        **gates,

        "unsupported_claims":
            unsupported_claims,

        "validation_status":
            "PASS" if passed else "FAIL",
    }
