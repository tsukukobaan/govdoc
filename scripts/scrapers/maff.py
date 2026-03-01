"""Scraper for Ministry of Agriculture, Forestry and Fisheries (農林水産省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class MAFFScraper(BaseScraper):
    ministry_slug = "maff"
    BASE_URL = "https://www.maff.go.jp"
    INDEX_URL = "https://www.maff.go.jp/j/council/"

    # Sub-domains that also host MAFF councils
    EXTRA_INDEXES = [
        ("https://www.rinya.maff.go.jp/j/rinsei/singikai/", "林政審議会"),
        ("https://www.jfa.maff.go.jp/j/council/index.html", "水産政策審議会"),
    ]

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()

        # 1. Scrape main council index
        print("  Fetching MAFF council index...")
        try:
            soup = self.fetch(self.INDEX_URL)
            council_pages = self._collect_council_links(soup, self.INDEX_URL)
            print(f"    -> {len(council_pages)} council pages found")
        except Exception as e:
            print(f"    Error: {e}")
            council_pages = []

        # 2. Scrape each council page
        for i, (url, name) in enumerate(council_pages):
            if i >= 60:  # Safety limit
                break
            try:
                page_records = self._scrape_council_page(url, name, seen_urls)
                records.extend(page_records)
                if page_records:
                    print(f"  [{i+1}/{len(council_pages)}] {name}: {len(page_records)} records")
            except Exception as e:
                print(f"  [{i+1}] Error on {name}: {e}")

        # 3. Scrape sub-domain indexes (rinya, jfa)
        for extra_url, extra_name in self.EXTRA_INDEXES:
            print(f"  Fetching {extra_name} from {extra_url}...")
            try:
                extra_records = self._scrape_subdomain(extra_url, extra_name, seen_urls)
                records.extend(extra_records)
                print(f"    -> {len(extra_records)} records")
            except Exception as e:
                print(f"    Error: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _collect_council_links(self, soup, base_url: str) -> list[tuple[str, str]]:
        """Collect links to council/subcommittee index pages."""
        pages = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())

            if not text or len(text) < 3:
                continue

            # Council pages under /j/council/
            if "/j/council/" in href or "/j/jas/" in href or "/nval/" in href:
                full_url = urljoin(base_url, href)
                if full_url not in seen and full_url != base_url:
                    seen.add(full_url)
                    pages.append((full_url, text))

        return pages

    def _scrape_council_page(self, url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        """Scrape a council page. May need to follow sub-links."""
        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        # Try to find meeting records directly on this page
        records = self._extract_meetings(soup, url, council_name, seen_urls)

        # If no records found, look for sub-council links and scrape those
        if not records:
            sub_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = normalize(a.get_text())
                if text and len(text) > 2:
                    full_url = urljoin(url, href)
                    # Follow sub-council index pages
                    if full_url != url and ("index" in href or "bukai" in href or "iinkai" in href):
                        if "/j/council/" in full_url or "/j/jas/" in full_url:
                            sub_links.append((full_url, f"{council_name} {text}"))

            for sub_url, sub_name in sub_links[:20]:
                try:
                    sub_soup = self.fetch(sub_url)
                    sub_records = self._extract_meetings(sub_soup, sub_url, sub_name, seen_urls)
                    records.extend(sub_records)
                except Exception:
                    pass

        return records

    def _extract_meetings(self, soup, base_url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        """Extract meeting records from a page."""
        records = []

        # Try table structure
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

                    doc_type = self._detect_doc_type(link_text, href)
                    if doc_type is None:
                        continue

                    full_url = urljoin(base_url, href)
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    records.append({
                        "committee_name": council_name,
                        "title": f"{council_name} {link_text}" if council_name not in link_text else link_text,
                        "url": full_url,
                        "meeting_date": meeting_date,
                        "doc_type": doc_type,
                    })

        # Try list structure
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

                    doc_type = self._detect_doc_type(link_text, href)
                    if doc_type is None:
                        continue

                    full_url = urljoin(base_url, href)
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    records.append({
                        "committee_name": council_name,
                        "title": link_text,
                        "url": full_url,
                        "meeting_date": meeting_date,
                        "doc_type": doc_type,
                    })

        return records

    def _scrape_subdomain(self, index_url: str, name: str, seen_urls: set[str]) -> list[dict]:
        """Scrape a sub-domain council index (rinya, jfa)."""
        records = []
        try:
            soup = self.fetch(index_url)
        except Exception:
            return records

        # First try to extract meetings directly
        records = self._extract_meetings(soup, index_url, name, seen_urls)

        # If it's just an index, follow sub-links
        if not records:
            sub_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = normalize(a.get_text())
                if text and len(text) > 2 and href != "#":
                    full_url = urljoin(index_url, href)
                    if full_url != index_url:
                        sub_links.append((full_url, f"{name} {text}"))

            for sub_url, sub_name in sub_links[:30]:
                try:
                    sub_soup = self.fetch(sub_url)
                    sub_records = self._extract_meetings(sub_soup, sub_url, sub_name, seen_urls)
                    records.extend(sub_records)
                except Exception:
                    pass

        return records

    def _detect_doc_type(self, text: str, href: str) -> str | None:
        """Detect document type. Returns None if not relevant."""
        if any(kw in text for kw in ["議事録", "議事概要", "議事要旨"]):
            if "要旨" in text or "概要" in text:
                return "summary"
            return "minutes"
        if any(kw in text for kw in ["配布資料", "配付資料", "資料"]):
            return "material"

        # URL patterns
        if "gijiroku" in href or "giji" in href:
            return "minutes"

        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = MAFFScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
