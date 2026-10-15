"""
CEREBRO relationship discovery.

Embedding similarity may generate candidate relationships.

Candidate relationships MUST NOT be silently promoted
to trusted relationships.
"""

import math


def cosine_similarity(vector_a, vector_b):

    if len(vector_a) != len(vector_b):
        raise ValueError(
            "Embedding dimensions do not match."
        )

    dot = sum(
        a * b
        for a, b in zip(vector_a, vector_b)
    )

    norm_a = math.sqrt(
        sum(a * a for a in vector_a)
    )

    norm_b = math.sqrt(
        sum(b * b for b in vector_b)
    )

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def relevance_label(
    similarity: float,
    *,
    high_threshold: float = 0.75,
    related_threshold: float = 0.55,
):
    """
    Thresholds are experimental PoC values inherited
    from EXP-KNOW-002. They are NOT calibrated production
    thresholds.
    """

    if similarity >= high_threshold:
        return "Highly Related"

    if similarity >= related_threshold:
        return "Related"

    return "Potential Connection"


def discover_candidate_relationships(
    embedding_records: list,
    *,
    high_threshold: float = 0.75,
    related_threshold: float = 0.55,
):
    """
    Compare every unique fragment pair and create
    semantic relationship candidates.
    """

    candidates = []

    relationship_number = 1

    for i in range(len(embedding_records)):

        for j in range(
            i + 1,
            len(embedding_records)
        ):

            source = embedding_records[i]
            target = embedding_records[j]

            similarity = cosine_similarity(
                source["embedding"],
                target["embedding"],
            )

            candidates.append({
                "candidate_relationship_id":
                    f"CAND-{relationship_number:04d}",

                "source_fragment_id":
                    source["fragment_id"],

                "target_fragment_id":
                    target["fragment_id"],

                "relationship_type":
                    "SEMANTIC_SIMILARITY",

                "similarity": similarity,

                "relevance": relevance_label(
                    similarity,
                    high_threshold=high_threshold,
                    related_threshold=related_threshold,
                ),

                "method": "cosine_similarity",

                "embedding_model":
                    source[
                        "embedding_metadata"
                    ]["model"],

                "status": "candidate",

                "human_validated": False,
            })

            relationship_number += 1

    return candidates
