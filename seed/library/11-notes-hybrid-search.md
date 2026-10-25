# Notes: Hybrid Search with Reciprocal Rank Fusion

Prepared by Joselito Dizon

_How CEREBRO combines keyword and semantic retrieval, and how to tell whether it works._

## Why hybrid

Written on 25 August 2026. Keyword search finds the exact acronym a person remembers; Semantic Search finds the passage that says the same thing in other words. Neither is enough alone.

## Reciprocal rank fusion

CEREBRO runs PostgreSQL full-text search and exact cosine similarity over stored vectors, then fuses the two rankings by reciprocal rank. A passage near the top of either list rises; one that both lists like rises most.

The fused passages are what Retrieval-Augmented Generation hands to the model, so retrieval quality caps answer quality.

## Checking it

Model Evaluation for search uses a small labelled set: for each question, which fragments should come back. Recall at five and the rank of the first correct fragment are the two numbers worth watching.

<sub>Illustrative sample document for the CEREBRO demo library.</sub>
