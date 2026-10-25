"""Print a library health report for one account. Read-only.

    docker compose exec api python -m app.tools.library_report --email you@example.com
    docker compose exec api python -m app.tools.library_report --email you@example.com \
        --json /tmp/report.json

Lives under `app/` so it ships in the API image and runs against the deployment's own database and
settings. See `app/services/library_health.py` for what each section measures.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db.session import SessionLocal
from app.services import library_health, users


def _section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _print(r: dict, top: int) -> None:
    t, e, links, similar = r["topics"], r["embeddings"], r["stated_links"], r["similar_documents"]

    _section("Topics")
    print(f"{t['documents']} registered documents, {t['distinct_topics']} distinct topics")
    if t["distinct_topics"]:
        share = t["single_document_topics"] / t["distinct_topics"]
        print(
            f"{t['single_document_topics']} topics ({share:.0%}) are confirmed on one document "
            "only, so they never link"
        )
    if t["documents_without_topics"]:
        print(
            f"{len(t['documents_without_topics'])} documents have no topics: "
            + "; ".join(t["documents_without_topics"][:top])
        )
    noise = [x for x in t["suspect_topics"] if x["severity"] == "noise"]
    check = [x for x in t["suspect_topics"] if x["severity"] == "check"]
    if noise:
        print(f"{len(noise)} confirmed topics are noise:")
        for x in noise[:top]:
            print(f"  {x['topic']!r} on {x['documents']} document(s): {x['reason']}")
    if check:
        print(
            f"{len(check)} single-word topics to check (keep the ones that name a subject): "
            + ", ".join(f"{x['topic']} ({x['documents']})" for x in check[: top * 2])
        )
    for v in t["variant_spellings"][:top]:
        print(f"Several spellings of one topic: {' / '.join(v['spellings'])}")
    print(
        "Most shared topics: "
        + ", ".join(
            f"{x['topic']} ({x['documents']})" for x in t["topics"][:top] if x["documents"] > 1
        )
        or "Most shared topics: none is shared by two documents"
    )
    g = t["galaxy_now"]
    print(
        f"\nThe Galaxy shows these {len(g['clusters'])} clusters today: " + ", ".join(g["clusters"])
    )
    if g["clusters_on_one_document"]:
        print(
            f"  of which {len(g['clusters_on_one_document'])} rest on a single document: "
            + ", ".join(g["clusters_on_one_document"])
        )
    print(f"  {g['edges']} edges, {g['recurring_edges']} of them backed by two or more documents")

    _section("Embeddings")
    if e["active"]:
        a = e["active"]
        print(
            f"Queries are embedded with {a['provider']} / {a['model']} "
            f"({a['dimensions']} dimensions)"
        )
    else:
        print("The active embedding provider could not be reached")
    print(
        f"{e['fragments_searchable']} of {e['fragments']} fragments are searchable with it; "
        f"{e['fragments_invisible']} are invisible"
    )
    for s in e["spaces"]:
        print(
            f"  {s['fragments']:>6} fragments embedded with "
            f"{s['provider']} / {s['model']} ({s['dimensions']})"
        )
    if e["documents_not_searchable"]:
        print(
            f"{len(e['documents_not_searchable'])} documents have no searchable fragment: "
            + "; ".join(e["documents_not_searchable"][:top])
        )

    _section(f"Stated links ({len(links)})")
    print(
        "A document naming another registered document in its own text, "
        "with the sentence that does."
    )
    for link in links[:top]:
        where = ", ".join(f"{k} {v}" for k, v in link["location"].items())
        print(
            f"  {link['source']}  --{link['relation']}-->  {link['target']}"
            + (f"  [{where}]" if where else "")
        )
        print(f'      "{link["evidence"][:160]}"')

    _section(f"Similar documents ({len(similar)})")
    print(
        "Each is among the other's nearest neighbours by averaged fragment vector. "
        "Similarity, not a relationship."
    )
    for p in similar[:top]:
        shared = (
            f"  shared topics: {', '.join(p['shared_topics'])}"
            if p["shared_topics"]
            else "  no shared topics"
        )
        print(f"  {p['score']:.3f}  {p['a']}  ~  {p['b']}\n        {shared}")

    _section("What to do")
    tips = []
    if t["distinct_topics"] and t["single_document_topics"] / t["distinct_topics"] > 0.5:
        tips.append(
            "Most topics sit on one document. Re-review documents and reuse a short shared "
            "vocabulary of topics."
        )
    if noise:
        tips.append(
            "Remove the topics flagged as noise. Dates, names and lone words crowd real subjects "
            "out of the Galaxy's twelve clusters. POST /api/graph/revalidate lists generic "
            "terms; ?apply=true removes them."
        )
        tips.append(
            "Topics drafted without a local model come from word statistics. "
            "With Ollama running and AI suggestions on, "
            "drafts are better, but still review them against one short shared vocabulary."
        )
    if t["variant_spellings"]:
        tips.append("Pick one spelling for each topic listed under 'several spellings'.")
    if e["fragments_invisible"]:
        tips.append(
            "Some fragments are in another embedding space. "
            "Re-embed them: POST /api/ml/embeddings/backfill."
        )
    if not links:
        tips.append(
            "No document names another by title. "
            "Stated links appear when documents refer to each other by name."
        )
    print("\n".join(f"- {tip}" for tip in tips) or "- Nothing stands out.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Library health report for one CEREBRO account (read-only)."
    )
    p.add_argument("--email", required=True, help="the account to report on")
    p.add_argument("--json", help="also write the full report to this file")
    p.add_argument(
        "--top", type=int, default=12, help="how many items to list per section (default 12)"
    )
    a = p.parse_args(argv)

    with SessionLocal() as db:
        user = users.get_by_email(db, a.email)
        if user is None:
            print(f"No account for {a.email}", file=sys.stderr)
            return 1
        r = library_health.report(db, user.id)
        db.rollback()  # read-only: make sure nothing is left pending

    print(f"Library health for {a.email}")
    _print(r, a.top)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
        print(f"\nFull report written to {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
