"""Genuine local semantic embeddings; no provider request or fabricated usage."""

from functools import lru_cache
from pathlib import Path

import numpy as np
from model2vec import StaticModel

MODEL = "minishlab/potion-multilingual-128M"
REVISION = "73908c3438cf03b6a01bcb9611d62b23d0726f08"
EMBEDDING_VERSION = f"model2vec-0.7.0:{MODEL}@{REVISION}:256"


@lru_cache(maxsize=2)
def load_model(path: str) -> StaticModel:
    folder = Path(path)
    if (folder / "revision.txt").read_text().strip() != f"{MODEL}@{REVISION}":
        raise ValueError("Embedding model revision mismatch; run make knowledge-model")
    return StaticModel.from_pretrained(folder, normalize=True)


def embed(texts: list[str], path: str) -> list[list[float]]:
    vectors = load_model(path).encode(texts, use_multiprocessing=False, max_length=512)
    values = np.asarray(vectors)
    if values.shape != (len(texts), 256) or not np.isfinite(values).all():
        raise ValueError("Invalid embeddings")
    if (np.linalg.norm(values, axis=1) < 0.001).any():
        raise ValueError("Empty embeddings")
    return values.tolist()
