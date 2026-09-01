"""
Generate and store embeddings for SBIR award abstracts using Voyage AI.

Model: voyage-3 (1024 dims, free tier: 50M tokens/month)
For ~180k awards with ~400-token average abstracts, expected usage: ~72M tokens.
At the free 50M limit, split into two monthly runs or upgrade to the paid tier
($0.06/1M tokens → ~$4.30 total).

Run standalone after awards are loaded:
    python -m pipeline.embed
"""

import logging
import time
from typing import Iterator

import voyageai
from tqdm import tqdm

from .config import VOYAGE_API_KEY, EMBED_MODEL, EMBED_BATCH_SIZE
from .transform import embed_text
from .load import fetch_unembedded_awards, upsert_embeddings

log = logging.getLogger(__name__)

_vo: voyageai.Client | None = None


def get_voyage() -> voyageai.Client:
    global _vo
    if _vo is None:
        _vo = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _vo


def _batches(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Call Voyage AI embeddings for a batch of texts."""
    client = get_voyage()
    result = client.embed(texts, model=EMBED_MODEL, input_type="document")
    return result.embeddings


def embed_and_store(awards: list[dict]) -> int:
    """
    Generate embeddings for a list of award dicts and upsert them.

    Returns total rows written.
    """
    total = 0
    with tqdm(total=len(awards), desc="Embedding", unit="award") as bar:
        for batch in _batches(awards, EMBED_BATCH_SIZE):
            texts = [embed_text(a) for a in batch]
            vectors = _embed_batch(texts)

            rows = [
                {
                    "award_id":  award["id"],
                    "embedding": vector,
                    "model":     EMBED_MODEL,
                }
                for award, vector in zip(batch, vectors)
            ]

            written = upsert_embeddings(rows)
            total += written
            bar.update(len(batch))
            time.sleep(0.05)  # stay well under rate limits

    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("Fetching awards without embeddings...")
    unembedded = fetch_unembedded_awards()
    log.info("Found %d awards to embed", len(unembedded))

    if not unembedded:
        log.info("Nothing to do.")
    else:
        written = embed_and_store(unembedded)
        log.info("Done. Wrote %d embeddings.", written)
