"""
CEREBRO embedding capability.

Defines CEREBRO-owned embedding records.

Model execution is performed by an adapter supplied
to this capability.
"""


def embed_fragments(
    fragments: list,
    embedding_function,
):
    """
    Generate embeddings for Knowledge Fragments.

    embedding_function must accept text and return:
    model, provider, embedding, dimensions.
    """

    records = []

    for fragment in fragments:

        result = embedding_function(
            fragment["content"]
        )

        records.append({
            "fragment_id": fragment["fragment_id"],

            "artifact_id": fragment["artifact_id"],

            "embedding": result["embedding"],

            "embedding_metadata": {
                "model": result["model"],
                "provider": result["provider"],
                "dimensions": result["dimensions"],
            },

            "provenance": {
                "source_fragment_id":
                    fragment["fragment_id"],

                "source_artifact_id":
                    fragment["artifact_id"],

                "source_sha256":
                    fragment["provenance"]["source_sha256"],
            },

            "status": "DERIVED",
        })

    return records
