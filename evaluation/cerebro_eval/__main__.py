"""Run CEREBRO's model evaluation and write the evidence folder.

    python -m cerebro_eval --out evidence/                      # everything
    python -m cerebro_eval --only retrieval,topics               # a subset
    python -m cerebro_eval --smoke --out /tmp/smoke              # code paths only, synthetic data

Results are written as JSON, with a manifest holding the SHA-256 of every
file, the CEREBRO commit, the model digests and the hardware.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import data as datasets
from .common import Run, ollama_models
from .engines import Embedder, LocalModel, digest_of, pick_models

EXPERIMENTS = ("retrieval", "topics", "grounded")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cerebro_eval",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out", type=Path, default=Path("evidence") / time.strftime("%Y%m%d-%H%M%S")
    )
    parser.add_argument(
        "--only", default=",".join(EXPERIMENTS), help="comma-separated: " + ", ".join(EXPERIMENTS)
    )
    parser.add_argument(
        "--ollama", default="http://localhost:11434", help="the Ollama daemon CEREBRO uses"
    )
    parser.add_argument(
        "--chat-model", help="default: the model CEREBRO would choose (qwen3 first)"
    )
    parser.add_argument(
        "--embed-model", help="default: the model CEREBRO would choose (mxbai-embed-large first)"
    )
    parser.add_argument(
        "--pg-url",
        help="a scratch PostgreSQL for the keyword search, e.g. "
        "postgresql+psycopg://eval:eval@127.0.0.1:55432/eval — never the CEREBRO database",
    )
    parser.add_argument(
        "--qa-per-kind", type=int, default=250, help="answerable and unanswerable questions, each"
    )
    parser.add_argument(
        "--llm-topics", type=int, default=400, help="posts the local model labels (0 to skip)"
    )
    parser.add_argument("--epochs", type=int, default=60, help="most epochs for the neural head")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="synthetic data: checks the code runs, measures nothing",
    )
    args = parser.parse_args(argv)

    chosen = [x.strip() for x in args.only.split(",") if x.strip()]
    unknown = set(chosen) - set(EXPERIMENTS)
    if unknown:
        parser.error(f"unknown experiment(s): {', '.join(sorted(unknown))}")

    run = Run(args.out, smoke=args.smoke)
    run.log(
        f"CEREBRO evaluation → {args.out}"
        + (" (SMOKE: numbers are meaningless)" if args.smoke else "")
    )

    try:
        installed = ollama_models(args.ollama)
    except OSError as exc:
        installed = []
        run.log(f"Ollama not reachable at {args.ollama}: {exc}")
    chat, embed = (
        pick_models(args.ollama, installed, args.chat_model, args.embed_model)
        if installed
        else (None, None)
    )
    run.log(f"chat model: {chat or 'none'} · embedding model: {embed or 'none'}")
    if not args.smoke and (chat is None or embed is None):
        run.log("A real run needs Ollama with a chat model and an embedding model. Stopping.")
        return 2

    embedders = {"hashing": Embedder(run, "hashing")}
    if embed:
        embedders["semantic"] = Embedder(
            run, "ollama", base_url=args.ollama, model=embed, digest=digest_of(installed, embed)
        )
    llm = LocalModel(args.ollama, chat) if chat else None

    results = {}
    if "retrieval" in chosen:
        from . import retrieval

        data = datasets.smoke_retrieval() if args.smoke else datasets.scifact(run)
        results["retrieval"] = retrieval.run(run, data, embedders, args.pg_url)
    if "topics" in chosen:
        from . import topics

        data = datasets.smoke_topics() if args.smoke else datasets.newsgroups(run)
        results["topics"] = topics.run(run, data, embedders, llm, args.llm_topics, args.epochs)
    if "grounded" in chosen:
        if llm is None:
            run.notes.append("grounded: skipped, no local chat model")
        else:
            from . import grounded

            data = datasets.smoke_squad() if args.smoke else datasets.squad(run)
            space = embedders.get("semantic", embedders["hashing"])
            results["grounded"] = grounded.run(run, data, space, llm, args.qa_per_kind)

    run.write("summary.json", results)
    run.manifest(
        {
            "experiments": chosen,
            "ollama": {
                "url": args.ollama,
                "chat_model": chat,
                "embedding_model": embed,
                "installed": [m for m in installed if m["name"] in {chat, embed}],
            },
            "embedders": {k: e.describe() for k, e in embedders.items()},
            "settings": {
                "qa_per_kind": args.qa_per_kind,
                "llm_topics": args.llm_topics,
                "epochs": args.epochs,
                "keyword_search_measured": bool(args.pg_url),
            },
        }
    )
    run.log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
