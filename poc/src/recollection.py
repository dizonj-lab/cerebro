"""
CEREBRO Assisted Recollection.

Deterministically resolves a Knowledge Fragment back to:
- its registered artifact,
- precise source location,
- exact source evidence,
- trusted relationships,
- candidate semantic relationships.

No LLM is required for source resolution.
"""


def find_fragment(
    fragment_id: str,
    knowledge_model: dict,
):
    """
    Resolve a Knowledge Fragment by canonical KF-* identity.
    """

    for fragment in knowledge_model["fragments"]:

        if fragment["fragment_id"] == fragment_id:
            return fragment

    raise KeyError(
        f"Knowledge Fragment not found: {fragment_id}"
    )


def resolve_source_evidence(
    fragment: dict,
    registered_artifact: dict,
    source_text: str,
):
    """
    Resolve exact evidence from the original source representation.
    """

    if (
        fragment["artifact_id"]
        != registered_artifact["artifact_id"]
    ):
        raise ValueError(
            "Fragment artifact does not match "
            "registered artifact."
        )

    if (
        fragment["provenance"]["source_sha256"]
        != registered_artifact["source"]["sha256"]
    ):
        raise ValueError(
            "Fragment source checksum does not match "
            "registered artifact."
        )

    location = fragment["source_location"]

    if location["type"] != "character_range":
        raise ValueError(
            "Unsupported source location type."
        )

    start_char = location["start_char"]
    end_char = location["end_char"]

    evidence = source_text[
        start_char:end_char
    ]

    if evidence != fragment["content"]:
        raise ValueError(
            "Resolved evidence does not match "
            "Knowledge Fragment content."
        )

    return evidence


def find_trusted_relationships(
    fragment_id: str,
    knowledge_model: dict,
):
    """
    Return trusted relationships involving the fragment.
    """

    relationships = []

    for relationship in (
        knowledge_model["trusted_relationships"]
    ):

        if (
            relationship["source_fragment_id"]
            == fragment_id
            or
            relationship["target_fragment_id"]
            == fragment_id
        ):
            relationships.append(relationship)

    return relationships


def find_candidate_relationships(
    fragment_id: str,
    candidate_relationships: list,
):
    """
    Return semantic candidates involving the fragment.

    Candidates remain clearly separated from trusted edges.
    """

    relationships = []

    for relationship in candidate_relationships:

        if (
            relationship["source_fragment_id"]
            == fragment_id
            or
            relationship["target_fragment_id"]
            == fragment_id
        ):
            relationships.append(relationship)

    return relationships


def recollect(
    fragment_id: str,
    *,
    knowledge_model: dict,
    registered_artifact: dict,
    source_text: str,
    candidate_relationships: list = None,
):
    """
    Build a deterministic Assisted Recollection record.
    """

    if candidate_relationships is None:
        candidate_relationships = []

    fragment = find_fragment(
        fragment_id,
        knowledge_model,
    )

    evidence = resolve_source_evidence(
        fragment,
        registered_artifact,
        source_text,
    )

    trusted = find_trusted_relationships(
        fragment_id,
        knowledge_model,
    )

    candidates = find_candidate_relationships(
        fragment_id,
        candidate_relationships,
    )

    return {
        "fragment_id": fragment_id,

        "knowledge": fragment["content"],

        "concepts": fragment.get(
            "concepts",
            []
        ),

        "source": {
            "artifact_id":
                registered_artifact["artifact_id"],

            "filename":
                registered_artifact["filename"],

            "sha256":
                registered_artifact["source"]["sha256"],

            "location":
                fragment["source_location"],

            "evidence":
                evidence,
        },

        "relationships": {
            "trusted": trusted,
            "candidate": candidates,
        },

        "integrity": {
            "source_resolved": True,
            "checksum_verified": True,
            "evidence_verified": True,
        },

        "status": "RECOLLECTED",
    }
