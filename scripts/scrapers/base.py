"""Base scraper for ministry advisory council pages."""
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from hashlib import md5
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError, HTTPError, Timeout

# Allow importing db module from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import connect_db

logger = logging.getLogger(__name__)

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
    use_playwright: bool = False
    playwright_fallback: bool = True
    playwright_channel: str | None = None  # e.g. "chrome" to use system Chrome

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

        # Playwright (lazy-initialized)
        self._playwright = None
        self._browser = None
        self._browser_context = None

    def _ensure_browser(self):
        """Lazily start Playwright and launch a Chromium browser."""
        if self._browser_context is not None:
            return
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        launch_opts: dict = {"headless": True}
        if self.playwright_channel:
            launch_opts["channel"] = self.playwright_channel
        self._browser = self._playwright.chromium.launch(**launch_opts)
        self._browser_context = self._browser.new_context(
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
        )

    def _fetch_with_playwright(self, url: str) -> BeautifulSoup:
        """Fetch a URL using a real Chromium browser."""
        self._ensure_browser()
        page = self._browser_context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            html = page.content()
            return BeautifulSoup(html, "html.parser")
        finally:
            page.close()

    def fetch(self, url: str) -> BeautifulSoup:
        """Fetch a URL and return BeautifulSoup object."""
        time.sleep(self.request_interval)
        if self.use_playwright:
            return self._fetch_with_playwright(url)
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except (HTTPError, ConnectionError, Timeout) as e:
            if not self.playwright_fallback:
                raise
            logger.info("requests failed for %s (%s), falling back to Playwright", url, e)
            return self._fetch_with_playwright(url)

    def close(self):
        """Shut down Playwright browser if it was started."""
        if self._browser_context is not None:
            self._browser_context.close()
            self._browser_context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def scrape(self) -> list[dict]:
        """Override this method. Return list of dicts with keys:
        committee_name, title, url, meeting_date (YYYY-MM-DD or None), doc_type
        """
        raise NotImplementedError

    def save_to_db(self, records: list[dict]):
        """Save scraped records to the database."""
        conn = connect_db()
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

    # --- Attachment extraction methods ---

    FILE_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt"]

    def _detect_file_type(self, url: str) -> str | None:
        """Detect file type from URL extension."""
        url_lower = url.lower().split("?")[0]
        for ext in self.FILE_EXTENSIONS:
            if url_lower.endswith(ext):
                return ext[1:]
        return None

    def extract_attachments_from_page(self, page_url: str) -> list[dict]:
        """Fetch an HTML meeting page and extract links to PDF/Excel/etc."""
        soup = self.fetch(page_url)
        attachments = []
        seen = set()
        for a in soup.find_all("a", href=True):
            full_url = urljoin(page_url, a["href"])
            file_type = self._detect_file_type(full_url)
            if file_type and full_url not in seen:
                seen.add(full_url)
                title = normalize(a.get_text()) if a.get_text().strip() else full_url.split("/")[-1]
                attachments.append({
                    "title": title,
                    "url": full_url,
                    "file_type": file_type,
                })
        return attachments

    def save_attachments_to_db(self, document_id: int, attachments: list[dict]):
        """Save extracted attachments to the attachments table."""
        if not attachments:
            return 0

        conn = connect_db()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get existing attachment URLs for this document
        cursor.execute(
            "SELECT url FROM attachments WHERE document_id = ?",
            (document_id,),
        )
        existing = {r[0] for r in cursor.fetchall()}

        inserted = 0
        for att in attachments:
            if att["url"] in existing:
                continue
            cursor.execute(
                """INSERT INTO attachments (document_id, title, url, file_type, is_downloaded, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (document_id, att["title"], att["url"], att["file_type"], now, now),
            )
            inserted += 1

        # Mark document as index page crawled
        cursor.execute(
            "UPDATE documents SET is_index_page = 1, index_crawled_at = ? WHERE id = ?",
            (now, document_id),
        )

        conn.commit()
        conn.close()
        return inserted
