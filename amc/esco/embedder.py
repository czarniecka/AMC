"""Text embeddings from an explicitly configured Ollama service."""

import os
from collections.abc import Sequence
from typing import Protocol

import numpy as np
import requests

DEFAULT_MODEL = "bge-m3"
BATCH = 32


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return one L2-normalized float32 row per text."""


def normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.where(norms == 0, 1, norms)).astype(np.float32)


class OllamaEmbedder:
    """Embed through POST /api/embed; install the model first with `ollama pull bge-m3`."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.name = model or os.getenv("ESCO_EMBED_MODEL", DEFAULT_MODEL)
        self._url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        rows: list[list[float]] = []
        with requests.Session() as session:
            session.trust_env = False
            for start in range(0, len(texts), BATCH):
                batch = list(texts[start : start + BATCH])
                response = session.post(
                    f"{self._url}/api/embed",
                    json={"model": self.name, "input": batch, "keep_alive": "15m"},
                    timeout=(5, 300),
                )
                response.raise_for_status()
                embeddings = response.json().get("embeddings", [])
                if len(embeddings) != len(batch):
                    raise ValueError("The embedding service returned an unexpected count.")
                rows.extend(embeddings)
        return normalize(np.asarray(rows, dtype=np.float32))
