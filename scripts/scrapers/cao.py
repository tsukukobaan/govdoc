"""Scraper for Cabinet Office (内閣府) advisory councils."""
from urllib.parse import urljoin, urlparse

from .base import BaseScraper, normalize, parse_date


class CAOScraper(BaseScraper):
    ministry_slug = "cao"
    INDEX_URL = "https://www.cao.go.jp/council.html"

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        print("  Fetching CAO council master index...")
        try:
            soup = self.fetch(self.INDEX_URL)
        except Exception as e:
            print(f"  Fatal: cannot fetch index: {e}")
            return records

        # Collect council page links (cao.go.jp domain including subdomains)
        council_pages: list[tuple[str, str]] = []
        seen_council: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())

            if not text or len(text) < 3:
                continue
            if href.startswith("#"):
                continue

            full_url = urljoin(self.INDEX_URL, href)
            parsed = urlparse(full_url)

            # Only cao.go.jp links (www, www5, www8, wwwa, etc.)
            if not parsed.hostname or not parsed.hostname.endswith("cao.go.jp"):
                continue
            if full_url == self.INDEX_URL:
                continue

            if full_url not in seen_council:
                seen_council.add(full_url)
                council_pages.append((full_url, text))

        print(f"  Found {len(council_pages)} council page links")

        for i, (url, name) in enumerate(council_pages):
            if i >= 100:
                break
            try:
                page_records = self._scrape_council(url, name, seen_urls, visited_pages)
                records.extend(page_records)
                if page_records:
                    print(f"  [{i+1}/{len(council_pages)}] {name}: {len(page_records)} records")
            except Exception as e:
                print(f"  [{i+1}] Error on {name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_council(self, url: str, council_name: str, seen_urls: set[str], visited_pages: set[str]) -> list[dict]:
        """Scrape a council page. Extract meetings from this page AND follow sub-links."""
        if url in visited_pages:
            return []
        visited_pages.add(url)

        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        records.extend(self._extract_meetings(soup, url, council_name, seen_urls))

        # Follow sub-links one level deeper
        sub_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())

            if not text or len(text) < 2:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue

            full_url = urljoin(url, href)
            parsed = urlparse(full_url)

            if not parsed.hostname or not parsed.hostname.endswith("cao.go.jp"):
                continue
            if full_url in visited_pages:
                continue

            is_sub_council = any(kw in text for kw in [
                "議事要旨", "議事録", "開催状況", "会議", "部会", "分科会",
                "小委員会", "ワーキング", "研究会", "懇談会", "検討会",
            ])
            is_meeting_list = any(kw in href for kw in [
                "gijiyoushi", "gijiroku", "kaisai", "shingi",
            ])

            if is_sub_council or is_meeting_list:
                sub_name = council_name if any(kw in text for kw in ["議事", "開催"]) else text
                sub_links.append((full_url, sub_name))

        for sub_url, sub_name in sub_links[:30]:
            if sub_url in visited_pages:
                continue
            visited_pages.add(sub_url)
            try:
                sub_soup = self.fetch(sub_url)
                sub_records = self._extract_meetings(sub_soup, sub_url, sub_name, seen_urls)
                records.extend(sub_records)
            except Exception:
                pass

        return records

    def _extract_meetings(self, soup, base_url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        """Extract meeting records from a page (tables or lists)."""
        records = []

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

                    title = f"{council_name} {link_text}" if council_name not in link_text else link_text

                    records.append({
                        "committee_name": council_name,
                        "title": title,
                        "url": full_url,
                        "meeting_date": meeting_date,
                        "doc_type": doc_type,
                    })

        for li in soup.find_all("li"):
            li_text = normalize(li.get_text())
            if len(li_text) < 10:
                continue

            meeting_date = parse_date(li_text)
            if not meeting_date:
                continue

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

    def _detect_doc_type(self, text: str, href: str) -> str | None:
        """Detect document type. Returns None if not relevant."""
        if any(kw in text for kw in ["議事録", "議事概要", "議事要旨"]):
            if "要旨" in text or "概要" in text:
                return "summary"
            return "minutes"
        if any(kw in text for kw in ["配布資料", "配付資料", "資料一覧", "資料"]):
            return "material"
        if "開催案内" in text:
            return "material"
        if "答申" in text or "報告書" in text:
            return "material"

        if any(kw in href for kw in ["gijiroku", "giji", "gijiyoushi"]):
            return "minutes"
        if "shiryou" in href or "siryou" in href:
            return "material"

        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = CAOScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
