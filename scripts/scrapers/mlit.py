"""Scraper for Ministry of Land, Infrastructure, Transport and Tourism (国土交通省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class MLITScraper(BaseScraper):
    ministry_slug = "mlit"
    BASE_URL = "https://www.mlit.go.jp"
    INDEX_URL = "https://www.mlit.go.jp/policy/shingikai/index.html"

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()

        print("  Fetching MLIT shingikai index...")
        try:
            soup = self.fetch(self.INDEX_URL)
        except Exception as e:
            print(f"  Fatal: cannot fetch index: {e}")
            return records

        # Collect all council page links (s1xx, s2xx, s3xx, s4xx, s5xx pattern)
        council_pages = []
        seen_council_urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())

            if not text or len(text) < 3:
                continue

            # Match shingikai council page links (e.g. s101_kokudo01.html, s303_tetsudo01.html)
            if "/policy/shingikai/" in href and re.search(r"s\d{3}_", href):
                full_url = urljoin(self.INDEX_URL, href)
                if full_url not in seen_council_urls:
                    seen_council_urls.add(full_url)
                    council_pages.append((full_url, text))

        print(f"  Found {len(council_pages)} council pages")

        # Scrape each council page for meeting records
        for i, (url, name) in enumerate(council_pages):
            try:
                page_records = self._scrape_council_page(url, name, seen_urls)
                records.extend(page_records)
                if page_records:
                    print(f"  [{i+1}/{len(council_pages)}] {name}: {len(page_records)} records")
            except Exception as e:
                print(f"  [{i+1}] Error on {name}: {e}")

            # Also try _past.html for historical records
            if url.endswith(".html"):
                past_url = url.replace(".html", "_past.html")
                try:
                    past_records = self._scrape_council_page(past_url, name, seen_urls)
                    records.extend(past_records)
                    if past_records:
                        print(f"    + past: {len(past_records)} records")
                except Exception:
                    pass  # past page may not exist

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_council_page(self, url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        """Scrape a council page for meeting records."""
        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        # MLIT council pages list meetings with dates and document links
        # Structure varies but commonly uses <table> or <ul>/<li>

        # Try table-based structure first
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                row_text = normalize(row.get_text())
                meeting_date = parse_date(row_text)

                for a in row.find_all("a", href=True):
                    link_text = normalize(a.get_text())
                    href = a["href"]

                    if not link_text or len(link_text) < 2:
                        continue

                    full_url = urljoin(url, href)
                    if full_url in seen_urls:
                        continue

                    doc_type = self._detect_doc_type(link_text, href)
                    if doc_type is None:
                        continue

                    seen_urls.add(full_url)
                    records.append({
                        "committee_name": council_name,
                        "title": f"{council_name} {link_text}" if council_name not in link_text else link_text,
                        "url": full_url,
                        "meeting_date": meeting_date,
                        "doc_type": doc_type,
                    })

        # Also try list-based structure
        if not records:
            for li in soup.find_all("li"):
                li_text = normalize(li.get_text())
                if len(li_text) < 10:
                    continue

                meeting_date = parse_date(li_text)

                for a in li.find_all("a", href=True):
                    link_text = normalize(a.get_text())
                    href = a["href"]

                    if not link_text or len(link_text) < 2:
                        continue

                    full_url = urljoin(url, href)
                    if full_url in seen_urls:
                        continue

                    doc_type = self._detect_doc_type(link_text, href)
                    if doc_type is None:
                        continue

                    seen_urls.add(full_url)
                    records.append({
                        "committee_name": council_name,
                        "title": f"{council_name} {link_text}" if council_name not in link_text else link_text,
                        "url": full_url,
                        "meeting_date": meeting_date,
                        "doc_type": doc_type,
                    })

        return records

    def _detect_doc_type(self, text: str, href: str) -> str | None:
        """Detect document type from link text and href. Returns None if not relevant."""
        # Check text
        if any(kw in text for kw in ["議事録", "議事概要", "議事要旨"]):
            if "要旨" in text or "概要" in text:
                return "summary"
            return "minutes"
        if any(kw in text for kw in ["配布資料", "配付資料", "資料", "参考資料"]):
            return "material"
        if "開催案内" in text or "開催通知" in text:
            return "material"

        # Check URL patterns
        if any(kw in href for kw in ["gijiroku", "giji"]):
            return "minutes"
        if any(kw in href for kw in ["siryou", "shiryo"]):
            return "material"

        # Not a document link
        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = MLITScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
