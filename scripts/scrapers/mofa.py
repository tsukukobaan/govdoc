"""Scraper for Ministry of Foreign Affairs (外務省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class MOFAScraper(BaseScraper):
    ministry_slug = "mofa"
    # MOFA uses Akamai CDN which blocks non-browser requests
    use_playwright = True
    playwright_channel = "chrome"
    request_interval = 3.0

    # MOFA has few formal advisory councils; pages are scattered
    INDEX_URLS = [
        "https://www.mofa.go.jp/mofaj/annai/shingikai/index.html",
        "https://www.mofa.go.jp/mofaj/annai/shingikai/jinji/index.html",
    ]

    # Known advisory/expert council pages (MOFA doesn't have a centralized listing)
    KNOWN_COUNCIL_URLS = [
        ("https://www.mofa.go.jp/mofaj/gaiko/oda/seisaku/yushikisya_k.html", "ODA有識者懇談会"),
        ("https://www.mofa.go.jp/mofaj/gaiko/kaku_yushikisya.html", "核不拡散・核軍縮に関する有識者懇談会"),
        ("https://www.mofa.go.jp/mofaj/gaiko/culture/kondankai1201/", "広報文化外交の制度的あり方に関する有識者懇談会"),
        ("https://www.mofa.go.jp/mofaj/gaiko/gaikou_anzen_think/", "外交・安全保障関係シンクタンクのあり方に関する有識者懇談会"),
    ]

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        # Scrape index pages
        for index_url in self.INDEX_URLS:
            print(f"  Fetching MOFA index: {index_url}")
            try:
                soup = self.fetch(index_url)
                records.extend(self._extract_meetings(soup, index_url, "外務人事審議会", seen_urls))
                # Also discover sub-links
                self._discover_councils(soup, index_url, visited_pages, seen_urls, records)
            except Exception as e:
                print(f"  Error fetching {index_url}: {e}")

        # Scrape known council pages
        for url, council_name in self.KNOWN_COUNCIL_URLS:
            if url in visited_pages:
                continue
            visited_pages.add(url)
            print(f"  Scraping known council: {council_name}")
            try:
                soup = self.fetch(url)
                page_records = self._extract_meetings(soup, url, council_name, seen_urls)
                records.extend(page_records)
                if page_records:
                    print(f"    {council_name}: {len(page_records)} records")
            except Exception as e:
                print(f"    Error on {council_name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _discover_councils(self, soup, base_url: str, visited_pages: set[str], seen_urls: set[str], records: list[dict]):
        """Discover council links from a page."""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if not text or len(text) < 3:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            full_url = urljoin(base_url, href)
            if "mofa.go.jp" not in full_url:
                continue
            if full_url in visited_pages:
                continue
            # Follow links that look like council pages
            if any(kw in text for kw in ["審議会", "懇談会", "有識者", "検討会"]):
                visited_pages.add(full_url)
                try:
                    sub_soup = self.fetch(full_url)
                    sub_records = self._extract_meetings(sub_soup, full_url, text, seen_urls)
                    records.extend(sub_records)
                    if sub_records:
                        print(f"    Discovered {text}: {len(sub_records)} records")
                except Exception:
                    pass

    def _extract_meetings(self, soup, base_url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        records = []

        for a in soup.find_all("a", href=True):
            link_text = normalize(a.get_text())
            href = a["href"]

            if not link_text or len(link_text) < 3:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue

            doc_type = self._detect_doc_type(link_text, href)
            if doc_type is None:
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            meeting_date = parse_date(link_text)
            if not meeting_date:
                parent = a.find_parent(["li", "td", "dd", "p"])
                if parent:
                    parent_text = normalize(parent.get_text())
                    if len(parent_text) < 500:
                        meeting_date = parse_date(parent_text)

            title = f"{council_name} {link_text}" if council_name not in link_text else link_text

            records.append({
                "committee_name": council_name,
                "title": title,
                "url": full_url,
                "meeting_date": meeting_date,
                "doc_type": doc_type,
            })

        return records

    def _detect_doc_type(self, text: str, href: str) -> str | None:
        if any(kw in text for kw in ["議事録", "議事概要", "議事要旨"]):
            if "要旨" in text or "概要" in text:
                return "summary"
            return "minutes"
        if any(kw in text for kw in ["配布資料", "配付資料", "資料一覧", "資料"]):
            return "material"
        if "答申" in text or "報告書" in text or "提言" in text:
            return "material"
        # Meeting pages (第N回)
        if re.search(r"第\d+回", text):
            return "minutes"

        if any(kw in href for kw in ["gijiroku", "giji", "gijiyoushi"]):
            return "minutes"
        if "shiryou" in href or "siryou" in href:
            return "material"

        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = MOFAScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
    scraper.close()
