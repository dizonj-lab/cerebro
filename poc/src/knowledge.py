"""
CEREBRO knowledge construction.

Constructs provenance-aware Knowledge Fragments from an
approved and registered artifact.

Semantic annotations supplied to this module are controlled
inputs. This module does not infer them automatically.
"""

from copy import deepcopy
from datetime import datetime, timezone


def construct_knowledge_model(
    *,
    knowledge_model_id: str,
    registered_artifact: dict,
    segments: list,
    fragment_annotations: list,
    trusted_relationships: list,
):
    """
    Construct trusted knowledge fragments from controlled,
    validated inputs.
    """

    if registered_artifact.get("status") != "REGISTERED":
        raise ValueError(
            "Knowledge construction requires "
            "a REGISTERED artifact."
        )

    if len(segments) != len(fragment_annotations):
        raise ValueError(
            "Each source segment requires exactly "
            "one controlled fragment annotation."
        )

    artifact_id = registered_artifact["artifact_id"]

    fragments = []

    for segment, annotation in zip(
        segments,
        fragment_annotations
    ):

        fragment = {
            "fragment_id": annotation["fragment_id"],

            "artifact_id": artifact_id,

            "content": segment["text"],

            "source_location": deepcopy(
                segment["source_location"]
            ),

            "concepts": deepcopy(
                annotation.get("concepts", [])
            ),

            "entities": deepcopy(
                annotation.get("entities", [])
            ),

            "temporal": {
                "source_date": annotation.get(
                    "source_date"
                ),

                "knowledge_date": annotation.get(
                    "knowledge_date"
                ),

                "ingested_at": annotation.get(
                    "ingested_at"
                ),
            },

            "provenance": {
                "source_artifact_id": artifact_id,
                "source_sha256":
                    registered_artifact["source"]["sha256"],
                "source_location_preserved": True,
            },

            "status": "TRUSTED",
        }

        fragments.append(fragment)

    return {
        "knowledge_model_id": knowledge_model_id,

        "artifact_id": artifact_id,

        "fragments": fragments,

        "trusted_relationships": deepcopy(
            trusted_relationships
        ),

        "constructed_at": (
            datetime.now(timezone.utc).isoformat()
        ),

        "status": "CONSTRUCTED",
    }
