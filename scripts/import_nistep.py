"""Import NISTEP metadata CSV into SQLite database."""

import csv
import sqlite3
import re
import unicodedata
from hashlib import md5
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DB_PATH = PROJECT_DIR / "dev.db"
CSV_PATH = PROJECT_DIR / "data" / "nistep" / "metadataset.csv"

# Organization name -> ministry slug mapping
MINISTRY_MAP = {
    "国会": "diet",
    "厚生労働省": "mhlw",
    "環境省": "env",
    "経済産業省": "meti",
    "文部科学省": "mext",
    "国土交通省": "mlit",
    "内閣府": "cao",
    "農林水産省": "maff",
    "総務省": "soumu",
    "首相官邸": "kantei",
    "財務省": "mof",
    "水産庁": "maff",
    "林野庁": "maff",
    "内閣官房": "cas",
    "防衛省": "mod",
    "日本学術会議": "cao",
}


def normalize_text(text: str) -> str:
    """Normalize full-width chars to half-width."""
    return unicodedata.normalize("NFKC", text).strip()


def make_slug(text: str) -> str:
    """Create a URL-safe slug from Japanese text using MD5 hash prefix + simplified name."""
    normalized = normalize_text(text)
    # Remove spaces and special chars for hash
    hash_input = re.sub(r"\s+", "", normalized)
    short_hash = md5(hash_input.encode("utf-8")).hexdigest()[:8]
    return short_hash


def parse_date(date_str: str) -> str | None:
    """Parse date string like '1997/8/7' to ISO format '1997-08-07'."""
    if not date_str or date_str.strip() == "":
        return None
    try:
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime(y, m, d).strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        pass
    return None


def normalize_url(url: str) -> str:
    """Ensure URL has https:// prefix."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def main():
    if not CSV_PATH.exists():
        print(f"CSV file not found: {CSV_PATH}")
        print("Download it first:")
        print("  curl -L https://raw.githubusercontent.com/NISTEP/minutes/master/metadataset.csv -o data/nistep/metadataset.csv")
        return

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run 'npx prisma migrate dev' first.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Load ministry slug -> id mapping
    cursor.execute("SELECT slug, id FROM ministries")
    ministry_ids = dict(cursor.fetchall())
    print(f"Loaded {len(ministry_ids)} ministries from DB")

    # Track committees: (ministry_id, slug) -> committee_id
    committee_cache: dict[tuple[int, str], int] = {}

    # Load existing committees
    cursor.execute("SELECT ministry_id, slug, id FROM committees")
    for row in cursor.fetchall():
        committee_cache[(row[0], row[1])] = row[2]

    # Read CSV
    print(f"Reading CSV: {CSV_PATH}")
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 5:
                rows.append(row)
    print(f"Read {len(rows)} rows")

    # Process rows
    seen_urls: set[str] = set()
    inserted = 0
    skipped_dup = 0
    skipped_unknown = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, row in enumerate(rows):
        date_str = row[0] if len(row) > 0 else ""
        org_name = row[1] if len(row) > 1 else ""
        committee_name = row[2] if len(row) > 2 else ""
        title = row[3] if len(row) > 3 else ""
        url = row[4] if len(row) > 4 else ""
        confirmed_str = row[5] if len(row) > 5 else ""

        # Normalize
        org_name = normalize_text(org_name)
        committee_name = normalize_text(committee_name)
        title = normalize_text(title)
        url = normalize_url(url)

        if not url:
            continue

        # Deduplicate by URL
        url_hash = md5(url.encode("utf-8")).hexdigest()
        if url_hash in seen_urls:
            skipped_dup += 1
            continue
        seen_urls.add(url_hash)

        # Map organization to ministry
        ministry_slug = MINISTRY_MAP.get(org_name)
        if not ministry_slug:
            skipped_unknown += 1
            if skipped_unknown <= 5:
                print(f"  Unknown org: '{org_name}' (row {i+1})")
            continue

        ministry_id = ministry_ids.get(ministry_slug)
        if not ministry_id:
            skipped_unknown += 1
            continue

        # Get or create committee
        committee_slug = make_slug(committee_name)
        cache_key = (ministry_id, committee_slug)

        if cache_key not in committee_cache:
            cursor.execute(
                """INSERT INTO committees (ministry_id, name, slug, category, is_active, document_count, created_at, updated_at)
                   VALUES (?, ?, ?, 'advisory_council', 1, 0, ?, ?)""",
                (ministry_id, committee_name, committee_slug, now, now),
            )
            committee_cache[cache_key] = cursor.lastrowid

        committee_id = committee_cache[cache_key]

        # Parse dates
        meeting_date = parse_date(date_str)
        confirmed_date = parse_date(confirmed_str)

        # Determine doc_type from title
        doc_type = "minutes"
        if "議事要旨" in title:
            doc_type = "summary"
        elif "配付資料" in title or "配布資料" in title or "資料" in title:
            doc_type = "material"

        # Insert document
        cursor.execute(
            """INSERT INTO documents (committee_id, title, url, meeting_date, doc_type, source, source_id, last_confirmed_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'nistep', ?, ?, ?, ?)""",
            (
                committee_id,
                title,
                url,
                meeting_date + "T00:00:00.000Z" if meeting_date else None,
                doc_type,
                url_hash,
                confirmed_date + "T00:00:00.000Z" if confirmed_date else None,
                now,
                now,
            ),
        )
        inserted += 1

        if (i + 1) % 10000 == 0:
            print(f"  Processed {i+1}/{len(rows)} rows...")
            conn.commit()

    conn.commit()

    # Update document counts on committees
    cursor.execute(
        """UPDATE committees SET document_count = (
            SELECT COUNT(*) FROM documents WHERE documents.committee_id = committees.id
        )"""
    )
    conn.commit()

    # Print summary
    cursor.execute("SELECT COUNT(*) FROM committees")
    committee_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM documents")
    document_count = cursor.fetchone()[0]

    print(f"\nImport complete!")
    print(f"  Documents inserted: {inserted}")
    print(f"  Duplicates skipped: {skipped_dup}")
    print(f"  Unknown orgs skipped: {skipped_unknown}")
    print(f"  Total committees: {committee_count}")
    print(f"  Total documents: {document_count}")

    # Show per-ministry breakdown
    cursor.execute(
        """SELECT m.name, COUNT(d.id) as doc_count, COUNT(DISTINCT c.id) as com_count
           FROM ministries m
           LEFT JOIN committees c ON c.ministry_id = m.id
           LEFT JOIN documents d ON d.committee_id = c.id
           GROUP BY m.id
           HAVING doc_count > 0
           ORDER BY doc_count DESC"""
    )
    print(f"\nPer-ministry breakdown:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} docs, {row[2]} committees")

    conn.close()


if __name__ == "__main__":
    main()
