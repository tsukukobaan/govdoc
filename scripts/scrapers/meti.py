"""Scraper for Ministry of Economy, Trade and Industry (経済産業省) advisory councils."""
import datetime
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class METIScraper(BaseScraper):
    ministry_slug = "meti"
    BASE_URL = "https://www.meti.go.jp"
    request_interval = 3.0
    use_playwright = True
    playwright_channel = "chrome"  # System Chrome needed to bypass TLS fingerprint block

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()

        # Scrape year-based index pages (2018-current)
        for year in range(2018, datetime.datetime.now().year + 1):
            url = f"{self.BASE_URL}/shingikai/index_{year}.html"
            print(f"  Fetching METI {year}...")
            try:
                page_records = self._scrape_year_page(url, year, seen_urls)
                records.extend(page_records)
                print(f"    -> {len(page_records)} records")
            except Exception as e:
                print(f"    Error: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_year_page(self, url: str, year: int, seen_urls: set[str]) -> list[dict]:
        """Scrape year-based index page for all meeting links."""
        records = []
        try:
            soup = self.fetch(url)
        except Exception as e:
            print(f"    Fetch error: {e}")
            return records

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())

            if not text or len(text) < 3:
                continue

            # Only include links under /shingikai/ that point to individual meeting pages
            # (not index pages or other navigation links)
            if "/shingikai/" not in href:
                continue

            # Skip navigation/index links
            if href.endswith("index.html") or "index_" in href:
                continue

            full_url = urljoin(url, href)

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract committee name from URL path
            # e.g. /shingikai/sankoshin/sangyo_gijutsu/innovation/008.html
            committee_name = self._extract_committee_name(href, text)

            # Extract date from text or surrounding context
            # METI uses <dl> structure: <dt>2025年3月31日</dt><dd><a>...</a></dd>
            meeting_date = parse_date(text)
            if not meeting_date:
                parent = a.parent
                if parent:
                    meeting_date = parse_date(normalize(parent.get_text()))
            if not meeting_date:
                # Check preceding <dt> element (the dl/dt/dd pattern)
                prev_dt = a.find_previous("dt")
                if prev_dt:
                    meeting_date = parse_date(normalize(prev_dt.get_text()))

            doc_type = "minutes"
            if "議事要旨" in text:
                doc_type = "summary"
            elif "報告" in text or "report" in href:
                doc_type = "material"

            records.append({
                "committee_name": committee_name,
                "title": text,
                "url": full_url,
                "meeting_date": meeting_date,
                "doc_type": doc_type,
            })

        return records

    def _extract_committee_name(self, href: str, text: str) -> str:
        """Extract committee name from link text."""
        # Try patterns like "第N回 産業構造審議会 ○○部会"
        match = re.search(r"(.+?(?:審議会|研究会|委員会|部会|分科会|ワーキング|WG|懇談会|検討会))", text)
        if match:
            name = match.group(1)
            # Remove leading "第N回 " prefix
            name = re.sub(r"^第\d+回\s*", "", name)
            if name:
                return name

        # Fallback: extract from URL path segments
        # /shingikai/enecho/denryoku_gas/... -> "enecho/denryoku_gas"
        parts = href.split("/")
        try:
            idx = parts.index("shingikai")
            if idx + 2 < len(parts):
                return "/".join(parts[idx + 1 : idx + 3])
        except ValueError:
            pass

        return text[:40]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = METIScraper()
    try:
        records = scraper.scrape()
        if records:
            scraper.save_to_db(records)
    finally:
        scraper.close()
