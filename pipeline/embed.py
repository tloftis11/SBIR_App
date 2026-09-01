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
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from tqdm import tqdm

from .config import VOYAGE_API_KEY, EMBED_MODEL, EMBED_BATCH_SIZE
from .transform import embed_text
from .load import stream_awards, get_embedded_ids_for, upsert_embeddings

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


@retry(
    retry=retry_if_exception_type(voyageai.error.RateLimitError),
    wait=wait_exponential(multiplier=1, min=20, max=120),
    stop=stop_after_attempt(8),
    before_sleep=lambda rs: log.warning(
        "Voyage AI rate limit — retrying in %.0fs (attempt %d)",
        rs.next_action.sleep, rs.attempt_number
    ),
)
def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Call Voyage AI embeddings for a batch of texts, with rate-limit retries."""
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
            try:
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
            except Exception as exc:
                log.warning("Batch failed (%s), skipping %d records: %s",
                            type(exc).__name__, len(batch), exc)
            finally:
                bar.update(len(batch))
                time.sleep(0.05)  # stay well under rate limits

    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("Streaming awards and embedding in pages...")

    total_written = 0
    total_skipped = 0
    page_num = 0

    for page in stream_awards(page_size=500):
        page_num += 1
        ids = [r["id"] for r in page]
        already = get_embedded_ids_for(ids)
        to_embed = [r for r in page if r["id"] not in already]
        total_skipped += len(already)

        if to_embed:
            written = embed_and_store(to_embed)
            total_written += written

        if page_num % 10 == 0:
            log.info("Page %d | embedded so far: %d | skipped: %d",
                     page_num, total_written, total_skipped)

    log.info("Done. Total written=%d skipped=%d", total_written, total_skipped)
