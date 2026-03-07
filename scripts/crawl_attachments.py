"""Crawl meeting pages to extract PDF/document attachment links.

Reads documents from dev.db whose URLs point to HTML pages (not .pdf),
fetches each page, and extracts links to PDF/Excel/etc files,
saving them to the attachments table.

Usage:
    python scripts/crawl_attachments.py                 # All eligible docs (2021+)
    python scripts/crawl_attachments.py --limit 20      # Test with 20 docs
    python scripts/crawl_attachments.py --ministry meti  # Single ministry
"""
import argparse
import sqlite3
import sys
import traceback
from pathlib import Path

from tqdm import tqdm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "dev.db"

# Map ministry slugs to scraper classes that know how to fetch their pages
SCRAPER_MAP = {
    "cao": ("scrapers.cao", "CAOScraper"),
    "cas": ("scrapers.cas", "CASScraper"),
    "env": ("scrapers.env", "ENVScraper"),
    "fsa": ("scrapers.fsa", "FSAScraper"),
    "kantei": ("scrapers.kantei", "KANTEIScraper"),
    "maff": ("scrapers.maff", "MAFFScraper"),
    "meti": ("scrapers.meti", "METIScraper"),
    "mext": ("scrapers.mext", "MEXTScraper"),
    "mhlw": ("scrapers.mhlw", "MHLWScraper"),
    "mlit": ("scrapers.mlit", "MLITScraper"),
    "mod": ("scrapers.mod", "MODScraper"),
    "mof": ("scrapers.mof", "MOFScraper"),
    "soumu": ("scrapers.soumu", "SOUMUScraper"),
}


def get_scraper(ministry_slug: str):
    """Lazily import and instantiate a scraper for the given ministry."""
    if ministry_slug not in SCRAPER_MAP:
        return None
    module_path, class_name = SCRAPER_MAP[ministry_slug]
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


def is_html_url(url: str) -> bool:
    """Check if URL likely points to an HTML page (not a direct file download)."""
    lower = url.lower().split("?")[0]
    file_exts = [".pdf", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt", ".zip", ".csv"]
    return not any(lower.endswith(ext) for ext in file_exts)


def main():
    parser = argparse.ArgumentParser(description="Crawl meeting pages for attachment links")
    parser.add_argument("--limit", type=int, default=0, help="Max number of documents to process (0=unlimited)")
    parser.add_argument("--ministry", type=str, default=None, help="Only process this ministry slug")
    parser.add_argument("--all-years", action="store_true", help="Process all years (default: 2021+)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find documents that haven't been crawled yet (is_index_page = 0 or NULL)
    query = """
        SELECT d.id, d.url, d.title, d.meeting_date, m.slug as ministry_slug
        FROM documents d
        JOIN committees c ON d.committee_id = c.id
        JOIN ministries m ON c.ministry_id = m.id
        WHERE (d.is_index_page = 0 OR d.is_index_page IS NULL)
          AND d.index_crawled_at IS NULL
    """
    params = []

    if not args.all_years:
        query += " AND d.meeting_date >= ?"
        params.append("2021-01-01T00:00:00.000Z")

    if args.ministry:
        query += " AND m.slug = ?"
        params.append(args.ministry)

    query += " ORDER BY d.meeting_date DESC"

    if args.limit > 0:
        query += f" LIMIT {args.limit}"

    cursor.execute(query, params)
    documents = cursor.fetchall()
    conn.close()

    # Filter to HTML URLs only
    documents = [d for d in documents if is_html_url(d["url"])]

    if not documents:
        print("No eligible documents to process.")
        return

    print(f"Found {len(documents)} documents to crawl for attachments.")

    # Group by ministry for scraper reuse
    by_ministry: dict[str, list] = {}
    for doc in documents:
        slug = doc["ministry_slug"]
        if slug not in by_ministry:
            by_ministry[slug] = []
        by_ministry[slug].append(doc)

    total_attachments = 0
    total_errors = 0

    for ministry_slug, docs in by_ministry.items():
        print(f"\n--- {ministry_slug} ({len(docs)} documents) ---")

        scraper = get_scraper(ministry_slug)
        if not scraper:
            print(f"  No scraper found for {ministry_slug}, using base scraper")
            from scrapers.base import BaseScraper
            scraper = BaseScraper()
            scraper.ministry_slug = ministry_slug

        try:
            for doc in tqdm(docs, desc=f"  {ministry_slug}", file=sys.stdout):
                try:
                    attachments = scraper.extract_attachments_from_page(doc["url"])
                    if attachments:
                        count = scraper.save_attachments_to_db(doc["id"], attachments)
                        total_attachments += count
                    else:
                        # Mark as crawled even if no attachments found
                        conn2 = sqlite3.connect(str(DB_PATH))
                        conn2.execute(
                            "UPDATE documents SET is_index_page = 1, index_crawled_at = datetime('now') WHERE id = ?",
                            (doc["id"],),
                        )
                        conn2.commit()
                        conn2.close()
                except Exception as e:
                    total_errors += 1
                    tqdm.write(f"  Error processing {doc['url']}: {e}")
                    if total_errors > 50:
                        tqdm.write("  Too many errors, stopping this ministry.")
                        break
        finally:
            scraper.close()

    print(f"\n{'='*50}")
    print(f"Total attachments extracted: {total_attachments}")
    print(f"Total errors: {total_errors}")


if __name__ == "__main__":
    main()
