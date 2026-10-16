"""Download only data files from an immutable revision; never remote Python/pickle."""

import os
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL = "minishlab/potion-multilingual-128M"
REVISION = "73908c3438cf03b6a01bcb9611d62b23d0726f08"

if __name__ == "__main__":
    target = Path(os.environ.get("KNOWLEDGE_MODEL_PATH", ".cache/knowledge-model"))
    snapshot_download(
        MODEL,
        revision=REVISION,
        local_dir=target,
        allow_patterns=["model.safetensors", "tokenizer.json", "config.json"],
    )
    (target / "revision.txt").write_text(f"{MODEL}@{REVISION}\n")
    print(f"Pinned embedding model installed in {target}")
