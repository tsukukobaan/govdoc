"""Base scraper for ministry advisory council pages."""
import re
import sqlite3
import time
import unicodedata
from datetime import datetime
from hashlib import md5
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PROJECT_DIR = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_DIR / "dev.db"

# Wareki (Japanese era) to seireki (Western calendar)
GENGOU = {"明治": 1868, "大正": 1912, "昭和": 1926, "平成": 1989, "令和": 2019}

WAREKI_PATTERN = re.compile(r"(令和|平成|昭和)(\d+)年(\d+)月(\d+)日")
WAREKI_SHORT_PATTERN = re.compile(r"\(R(\d{2})\.(\d+)\.(\d+)\)")


def normalize(text: str) -> str:
    """Normalize full-width to half-width and strip."""
    return unicodedata.normalize("NFKC", text).strip()


def wareki_to_date(gengou: str, nen: int, month: int, day: int) -> str:
    """Convert wareki to ISO date string."""
    year = GENGOU[gengou] + nen - 1
    return f"{year}-{month:02d}-{day:02d}"


def parse_wareki(text: str) -> str | None:
    """Extract and convert wareki date from text."""
    text = normalize(text)
    m = WAREKI_PATTERN.search(text)
    if m:
        return wareki_to_date(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    # Try short format (R08.3.2)
    m = WAREKI_SHORT_PATTERN.search(text)
    if m:
        year = 2019 + int(m.group(1)) - 1
        return f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def parse_seireki(text: str) -> str | None:
    """Extract Western calendar date (YYYY/M/D or YYYY年M月D日)."""
    text = normalize(text)
    m = re.search(r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def parse_date(text: str) -> str | None:
    """Try all date parsing methods."""
    return parse_seireki(text) or parse_wareki(text)


class BaseScraper:
    """Base class for ministry scrapers."""

    ministry_slug: str = ""
    request_interval: float = 2.0

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GovDocIndex/1.0 (research project; +https://github.com/govdoc-index)",
            "Accept-Language": "ja,en;q=0.9",
        })
        # Retry config
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def fetch(self, url: str) -> BeautifulSoup:
        """Fetch a URL and return BeautifulSoup object."""
        time.sleep(self.request_interval)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return BeautifulSoup(resp.text, "html.parser")

    def scrape(self) -> list[dict]:
        """Override this method. Return list of dicts with keys:
        committee_name, title, url, meeting_date (YYYY-MM-DD or None), doc_type
        """
        raise NotImplementedError

    def save_to_db(self, records: list[dict]):
        """Save scraped records to the database."""
        if not DB_PATH.exists():
            print(f"Database not found: {DB_PATH}")
            return

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Get ministry id
        cursor.execute("SELECT id FROM ministries WHERE slug = ?", (self.ministry_slug,))
        row = cursor.fetchone()
        if not row:
            print(f"Ministry '{self.ministry_slug}' not found")
            return
        ministry_id = row[0]

        # Committee cache
        committee_cache: dict[str, int] = {}
        cursor.execute("SELECT name, id FROM committees WHERE ministry_id = ?", (ministry_id,))
        for r in cursor.fetchall():
            committee_cache[r[0]] = r[1]

        # Existing URLs to avoid duplicates
        cursor.execute(
            """SELECT d.url FROM documents d
               JOIN committees c ON d.committee_id = c.id
               WHERE c.ministry_id = ?""",
            (ministry_id,),
        )
        existing_urls = {r[0] for r in cursor.fetchall()}

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0
        skipped = 0

        for rec in records:
            url = rec["url"]
            if url in existing_urls:
                skipped += 1
                continue
            existing_urls.add(url)

            committee_name = rec["committee_name"]
            if committee_name not in committee_cache:
                slug = md5(committee_name.encode("utf-8")).hexdigest()[:8]
                # Check if slug already exists (collision or from NISTEP data)
                cursor.execute(
                    "SELECT id FROM committees WHERE ministry_id = ? AND slug = ?",
                    (ministry_id, slug),
                )
                existing = cursor.fetchone()
                if existing:
                    committee_cache[committee_name] = existing[0]
                else:
                    cursor.execute(
                        """INSERT INTO committees (ministry_id, name, slug, category, is_active, document_count, created_at, updated_at)
                           VALUES (?, ?, ?, 'advisory_council', 1, 0, ?, ?)""",
                        (ministry_id, committee_name, slug, now, now),
                    )
                    committee_cache[committee_name] = cursor.lastrowid

            committee_id = committee_cache[committee_name]
            meeting_date = rec.get("meeting_date")
            if meeting_date:
                meeting_date = f"{meeting_date}T00:00:00.000Z"

            cursor.execute(
                """INSERT INTO documents (committee_id, title, url, meeting_date, doc_type, source, source_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'crawl', ?, ?, ?)""",
                (
                    committee_id,
                    rec.get("title", ""),
                    url,
                    meeting_date,
                    rec.get("doc_type", "minutes"),
                    md5(url.encode("utf-8")).hexdigest(),
                    now,
                    now,
                ),
            )
            inserted += 1

        # Update document counts
        cursor.execute(
            """UPDATE committees SET document_count = (
                SELECT COUNT(*) FROM documents WHERE documents.committee_id = committees.id
            ) WHERE ministry_id = ?""",
            (ministry_id,),
        )
        conn.commit()
        conn.close()

        print(f"  Inserted: {inserted}, Skipped (duplicates): {skipped}")
        return inserted
