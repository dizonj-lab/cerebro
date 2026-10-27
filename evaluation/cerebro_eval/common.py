"""What every experiment shares: where results go, how inputs are fetched,
and the record that makes a result traceable.

A number in the report is only as good as the record behind it, so every run
writes down what produced it: the CEREBRO commit, the exact Ollama model
digests, the hardware, the library versions, and the SHA-256 of every
dataset file read and every file written. Nothing here is estimated or
copied from a spec sheet — the GPU name and peak memory are read from the
device that ran.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

CACHE = Path(os.environ.get("CEREBRO_EVAL_CACHE", Path.home() / ".cache" / "cerebro-eval"))
REPO = Path(__file__).resolve().parents[2]
SEED = 20261027


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(urls: list[str], name: str) -> Path:
    """A dataset file, downloaded once into the cache. The first URL that answers wins."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if target.exists() and target.stat().st_size:
        return target
    errors = []
    for url in urls:
        try:
            partial = target.with_suffix(target.suffix + ".part")
            request = urllib.request.Request(url, headers={"User-Agent": "cerebro-eval"})
            with (
                urllib.request.urlopen(request, timeout=120) as response,
                open(partial, "wb") as out,
            ):  # noqa: S310
                while block := response.read(1 << 20):
                    out.write(block)
            partial.rename(target)
            return target
        except OSError as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(f"Could not download {name}:\n  " + "\n  ".join(errors))


@dataclass
class Run:
    """One evaluation run: an output folder and everything recorded about it."""

    out: Path
    smoke: bool = False
    datasets: list[dict] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self._log = open(self.out / "run.log", "a", encoding="utf-8")

    def log(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        print(line, flush=True)
        self._log.write(line + "\n")
        self._log.flush()

    def dataset(self, name: str, path: Path, source: str, licence: str) -> None:
        self.datasets.append(
            {
                "name": name,
                "file": path.name,
                "sha256": sha256_of(path),
                "bytes": path.stat().st_size,
                "source": source,
                "licence": licence,
            }
        )

    def write(self, name: str, payload: object) -> Path:
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, default=_plain)
        self.log(f"wrote {name}")
        return path

    @contextmanager
    def timed(self, label: str):
        started = time.perf_counter()
        self.log(f"-- {label}")
        try:
            yield
        finally:
            self.timings[label] = round(time.perf_counter() - started, 1)
            self.log(f"   {label}: {self.timings[label]} s")

    def manifest(self, extra: dict) -> Path:
        """Every output file with its SHA-256, and what produced them."""
        files = [
            {
                "path": str(p.relative_to(self.out)),
                "sha256": sha256_of(p),
                "bytes": p.stat().st_size,
            }
            for p in sorted(self.out.rglob("*"))
            if p.is_file() and p.name not in {"manifest.json", "run.log"}
        ]
        return self.write(
            "manifest.json",
            {
                "smoke": self.smoke,
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "cerebro_commit": _git("rev-parse", "HEAD"),
                "cerebro_dirty": bool(_git("status", "--porcelain")),
                "environment": environment(),
                "datasets": self.datasets,
                "timings_s": self.timings,
                "notes": self.notes,
                **extra,
                "files": files,
            },
        )


def _plain(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not serialisable: {type(value)}")


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def environment() -> dict:
    """The machine that ran, read from the machine."""
    import numpy
    import sklearn

    info: dict = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": numpy.__version__,
        "scikit_learn": sklearn.__version__,
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info["gpu"] = props.name
            info["gpu_memory_gb"] = round(props.total_memory / 2**30, 1)
    except ImportError:
        info["torch"] = None
    return info


def ollama_models(base_url: str) -> list[dict]:
    """What the daemon has installed, with the digest that pins each model exactly."""
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=10) as response:  # noqa: S310
        body = json.loads(response.read())
    return [
        {
            "name": m.get("name"),
            "digest": m.get("digest"),
            "size_bytes": m.get("size"),
            "parameter_size": (m.get("details") or {}).get("parameter_size"),
            "quantization": (m.get("details") or {}).get("quantization_level"),
            "family": (m.get("details") or {}).get("family"),
        }
        for m in body.get("models", [])
    ]
