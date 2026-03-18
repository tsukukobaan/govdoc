"""Scraper for Digital Agency (デジタル庁) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


def _clean_date_text(text: str) -> str:
    """Remove inline seireki annotations like (2022年) from wareki dates."""
    return re.sub(r"\(\d{4}年\)", "", text)


class DIGITALScraper(BaseScraper):
    ministry_slug = "digital"
    INDEX_URL = "https://www.digital.go.jp/councils"

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()

        print("  Fetching Digital Agency councils index...")
        try:
            soup = self.fetch(self.INDEX_URL)
        except Exception as e:
            print(f"  Fatal: cannot fetch index: {e}")
            return records

        # Collect links to individual council pages
        council_links: list[tuple[str, str]] = []
        seen_council: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if not text or len(text) < 3:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            # Council pages are under /councils/{slug}
            if re.match(r"/councils/[a-z0-9\-]+$", href):
                full_url = urljoin(self.INDEX_URL, href)
                if full_url not in seen_council:
                    seen_council.add(full_url)
                    council_links.append((full_url, text))

        print(f"  Found {len(council_links)} council pages")

        for i, (url, council_name) in enumerate(council_links):
            try:
                page_records = self._scrape_council(url, council_name, seen_urls)
                records.extend(page_records)
                if page_records:
                    print(f"  [{i+1}/{len(council_links)}] {council_name}: {len(page_records)} records")
            except Exception as e:
                print(f"  [{i+1}] Error on {council_name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_council(self, url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        """Scrape an individual council page for meeting links."""
        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        # Meeting links are in <ul>/<li> under 開催状況 section
        # Each entry: 会議名（第N回）（YYYY年M月D日開催）
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if not text or len(text) < 5:
                continue

            # Meeting pages are /councils/{slug}/{uuid}
            if not re.search(r"/councils/[a-z0-9\-]+/[a-f0-9\-]{30,}", href):
                continue

            full_url = urljoin(url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract date from link text or parent
            # Digital Agency uses 令和N年(YYYY年)M月D日 format — strip inline seireki
            meeting_date = parse_date(_clean_date_text(text))
            if not meeting_date:
                parent = a.find_parent("li")
                if parent:
                    meeting_date = parse_date(_clean_date_text(normalize(parent.get_text())))

            records.append({
                "committee_name": council_name,
                "title": text,
                "url": full_url,
                "meeting_date": meeting_date,
                "doc_type": "minutes",
            })

        return records


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = DIGITALScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
