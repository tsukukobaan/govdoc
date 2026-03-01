"""Scraper for Ministry of Health, Labour and Welfare (厚生労働省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class MHLWScraper(BaseScraper):
    ministry_slug = "mhlw"
    INDEX_URL = "https://www.mhlw.go.jp/stf/shingi/indexshingi.html"
    BASE_URL = "https://www.mhlw.go.jp"

    def scrape(self) -> list[dict]:
        records = []
        print("Fetching MHLW shingi index...")
        soup = self.fetch(self.INDEX_URL)

        # Collect council links from the nested list structure
        council_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if "/stf/shingi/" in href and text and len(text) > 2:
                full_url = urljoin(self.BASE_URL, href)
                council_links.append((full_url, text))

        print(f"  Found {len(council_links)} council page links")

        # Scrape each council page (limit to avoid overloading)
        for i, (url, name) in enumerate(council_links):
            if i >= 100:  # Safety limit
                break
            try:
                page_records = self._scrape_council_page(url, name)
                records.extend(page_records)
                if page_records:
                    print(f"  [{i+1}/{len(council_links)}] {name}: {len(page_records)} records")
            except Exception as e:
                print(f"  [{i+1}] Error on {name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_council_page(self, url: str, council_name: str) -> list[dict]:
        """Scrape individual council page for meeting records."""
        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        # MHLW council pages often have tables with meeting info
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue

                row_text = normalize(row.get_text())
                meeting_date = parse_date(row_text)

                # Find links in the row
                for a in row.find_all("a", href=True):
                    link_text = normalize(a.get_text())
                    href = a["href"]

                    if not link_text or len(link_text) < 2:
                        continue

                    # Filter for relevant links
                    is_relevant = any(kw in link_text for kw in [
                        "議事録", "議事要旨", "資料", "概要", "報告",
                    ]) or any(kw in href for kw in [
                        "gijiroku", "giji", "txt", "shingi",
                    ])

                    if not is_relevant:
                        continue

                    full_url = urljoin(url, href)

                    doc_type = "minutes"
                    if "議事要旨" in link_text or "概要" in link_text:
                        doc_type = "summary"
                    elif "資料" in link_text:
                        doc_type = "material"

                    title = f"{council_name} {link_text}" if council_name not in link_text else link_text

                    records.append({
                        "committee_name": council_name,
                        "title": title,
                        "url": full_url,
                        "meeting_date": meeting_date,
                        "doc_type": doc_type,
                    })

        # Also check for simple link lists (ul/li structure)
        if not records:
            for a in soup.find_all("a", href=True):
                text = normalize(a.get_text())
                href = a["href"]
                if any(kw in text for kw in ["議事録", "議事要旨"]):
                    full_url = urljoin(url, href)
                    parent_text = normalize(a.parent.get_text()) if a.parent else ""
                    meeting_date = parse_date(parent_text)

                    doc_type = "summary" if "議事要旨" in text else "minutes"

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
    scraper = MHLWScraper()
    records = scraper.scrape()
    scraper.save_to_db(records)
