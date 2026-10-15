"""
CEREBRO Ollama adapter.

Third-party/model-specific behavior belongs here.
CEREBRO Core must not depend directly on Ollama.
"""

import json
import urllib.request
import urllib.error


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:latest"


def generate_json(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_URL,
    temperature: float = 0.0,
    timeout: int = 120,
):
    """
    Execute a local Ollama generation request and return parsed JSON.
    """

    url = f"{base_url}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama request failed: {exc}"
        ) from exc

    raw_response = result.get("response", "")

    try:
        parsed = json.loads(raw_response)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Ollama returned invalid JSON."
        ) from exc

    return {
        "model": model,
        "provider": "ollama",
        "response": parsed,
    }



def generate_embedding(
    text: str,
    *,
    model: str = "mxbai-embed-large:latest",
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout: int = 120,
):
    """
    Generate one local embedding using Ollama.

    Uses the /api/embeddings endpoint validated by
    EXP-KNOW-002.
    """

    url = f"{base_url}/api/embeddings"

    payload = {
        "model": model,
        "prompt": text,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama embedding request failed: {exc}"
        ) from exc

    embedding = result.get("embedding")

    if not isinstance(embedding, list):
        raise ValueError(
            "Ollama returned no valid embedding."
        )

    return {
        "model": model,
        "provider": "ollama",
        "embedding": embedding,
        "dimensions": len(embedding),
    }
