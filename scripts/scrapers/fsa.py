"""Scraper for Financial Services Agency (金融庁) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class FSAScraper(BaseScraper):
    ministry_slug = "fsa"
    INDEX_URL = "https://www.fsa.go.jp/singi/"

    def scrape(self) -> list[dict]:
        records = []
        print("Fetching FSA singi index...")
        soup = self.fetch(self.INDEX_URL)

        # Find all links to council subpages
        council_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            # Links to council index pages
            if "/singi/" in href and href != "/singi/" and text:
                full_url = urljoin(self.INDEX_URL, href)
                if full_url not in [cl[0] for cl in council_links]:
                    council_links.append((full_url, text))

        print(f"  Found {len(council_links)} council links")

        for url, council_name in council_links:
            if "index" not in url and not url.endswith("/"):
                # This might be a direct document link
                continue
            try:
                records.extend(self._scrape_council(url, council_name))
            except Exception as e:
                print(f"  Error scraping {council_name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_council(self, index_url: str, council_name: str) -> list[dict]:
        """Scrape a specific council's page for meeting records."""
        records = []
        try:
            soup = self.fetch(index_url)
        except Exception:
            return records

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if not text:
                continue

            # Look for meeting-related links
            is_minutes = any(kw in text for kw in ["議事録", "議事要旨", "資料", "概要"])
            is_meeting_page = any(kw in href for kw in ["gijiroku", "giji", "siryou", "gaiyou"])

            if not is_minutes and not is_meeting_page:
                continue

            full_url = urljoin(index_url, href)

            # Determine doc type
            doc_type = "minutes"
            if "議事要旨" in text or "概要" in text:
                doc_type = "summary"
            elif "資料" in text:
                doc_type = "material"

            # Try to extract date from surrounding text
            parent = a.parent
            parent_text = normalize(parent.get_text()) if parent else ""
            meeting_date = parse_date(parent_text)

            records.append({
                "committee_name": council_name,
                "title": text,
                "url": full_url,
                "meeting_date": meeting_date,
                "doc_type": doc_type,
            })

        return records


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = FSAScraper()
    records = scraper.scrape()
    scraper.save_to_db(records)
