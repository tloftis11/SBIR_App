"""
Download the SBIR bulk CSV and load it into Supabase.

This is the primary ingestion path when the api.sbir.gov endpoint is
unreachable (e.g. corporate networks that block that subdomain).

Usage:
    # Download + ingest in one step:
    python -m pipeline.ingest_csv

    # Use a CSV you already downloaded:
    python -m pipeline.ingest_csv --file path/to/award_data.csv

    # Dry-run: print first 5 normalized rows without writing to Supabase:
    python -m pipeline.ingest_csv --dry-run
"""

import csv
import io
import logging
import argparse
import time
from pathlib import Path

import httpx
from tqdm import tqdm

from .transform import normalize
from .load import upsert_awards

log = logging.getLogger(__name__)

BULK_CSV_URL = "https://data.www.sbir.gov/awarddatapublic/award_data.csv"
UPSERT_BATCH = 500


def download_csv(dest: Path) -> Path:
    """Stream-download the bulk CSV file with a progress bar."""
    log.info("Downloading %s → %s", BULK_CSV_URL, dest)
    with httpx.stream("GET", BULK_CSV_URL, follow_redirects=True, timeout=300) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc="Downloading CSV"
        ) as bar:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                bar.update(len(chunk))
    log.info("Download complete: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def ingest_file(csv_path: Path, dry_run: bool = False, start_year: int | None = None) -> int:
    """
    Parse the CSV and upsert records into Supabase.

    Returns total rows written.
    """
    total_written = 0
    total_skipped = 0
    total_filtered = 0
    batch: list[dict] = []

    with open(csv_path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)  # count for the progress bar

    log.info("Parsed %d rows from CSV", len(rows))
    if start_year:
        log.info("Filtering to award_year >= %d", start_year)

    with tqdm(total=len(rows), desc="Loading awards", unit="row") as bar:
        for raw in rows:
            # Year filter: check raw CSV field before normalizing to save time
            if start_year:
                raw_year = raw.get("Award Year") or raw.get("award_year") or raw.get("year") or ""
                try:
                    if int(raw_year) < start_year:
                        total_filtered += 1
                        bar.update(1)
                        continue
                except (ValueError, TypeError):
                    pass  # can't parse year — let normalize handle it

            record = normalize(raw)
            if record is None:
                total_skipped += 1
                bar.update(1)
                continue

            if dry_run:
                print(record)
                bar.update(1)
                total_written += 1
                if total_written >= 5:
                    print("... (dry-run, stopping at 5 rows)")
                    break
                continue

            batch.append(record)
            if len(batch) >= UPSERT_BATCH:
                upsert_awards(batch)
                total_written += len(batch)
                batch = []

            bar.update(1)

    if batch and not dry_run:
        upsert_awards(batch)
        total_written += len(batch)

    log.info("Done. Written=%d Skipped=%d Filtered(year)=%d", total_written, total_skipped, total_filtered)
    return total_written


def main():
    parser = argparse.ArgumentParser(description="Ingest SBIR bulk CSV into Supabase")
    parser.add_argument("--file", type=Path, metavar="PATH",
                        help="Path to a pre-downloaded award_data.csv (skips download)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first 5 normalized rows without writing to DB")
    parser.add_argument("--start-year", type=int, metavar="YEAR",
                        help="Only ingest awards from this year onwards (e.g. 2024)")
    parser.add_argument("--dest", type=Path, metavar="PATH", default=Path("award_data_fresh.csv"),
                        help="Destination path for downloaded CSV (default: award_data_fresh.csv)")
    args = parser.parse_args()

    csv_path = args.file
    if csv_path is None:
        csv_path = args.dest
        if not csv_path.exists():
            download_csv(csv_path)
        else:
            log.info("Using existing %s", csv_path)

    t0 = time.time()
    written = ingest_file(csv_path, dry_run=args.dry_run, start_year=args.start_year)
    elapsed = time.time() - t0
    log.info("Ingest complete: %d rows in %.1f min", written, elapsed / 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
