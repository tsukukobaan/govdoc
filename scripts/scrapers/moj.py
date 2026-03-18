"""Scraper for Ministry of Justice (法務省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class MOJScraper(BaseScraper):
    ministry_slug = "moj"
    # 審議会 + 検討会等 + 委員会
    INDEX_URLS = [
        "https://www.moj.go.jp/shingikai_index.html",
        "https://www.moj.go.jp/kentoukai_index.html",
        "https://www.moj.go.jp/iinkai_index.html",
    ]

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        for index_url in self.INDEX_URLS:
            print(f"  Fetching MOJ index: {index_url}")
            try:
                soup = self.fetch(index_url)
            except Exception as e:
                print(f"  Error fetching {index_url}: {e}")
                continue

            # Collect council links from h3 headings
            council_links: list[tuple[str, str]] = []
            seen_council: set[str] = set()
            for h3 in soup.find_all("h3"):
                a = h3.find("a", href=True)
                if not a:
                    continue
                text = normalize(a.get_text())
                if not text or len(text) < 3:
                    continue
                full_url = urljoin(index_url, a["href"])
                if "moj.go.jp" not in full_url:
                    continue
                if full_url not in seen_council:
                    seen_council.add(full_url)
                    council_links.append((full_url, text))

            # Also collect links from section divs (some pages use <a> directly)
            for a in soup.find_all("a", href=True):
                text = normalize(a.get_text())
                if not text or len(text) < 5:
                    continue
                href = a["href"]
                if href.startswith("#") or href.startswith("mailto:"):
                    continue
                full_url = urljoin(index_url, href)
                if "moj.go.jp" not in full_url:
                    continue
                if full_url in seen_council:
                    continue
                # Follow links that look like council/committee pages
                if any(kw in href for kw in ["shingi", "kentou", "iinkai", "bukai"]):
                    seen_council.add(full_url)
                    council_links.append((full_url, text))

            print(f"  Found {len(council_links)} council links from {index_url}")

            for i, (url, council_name) in enumerate(council_links):
                try:
                    page_records = self._scrape_council(url, council_name, seen_urls, visited_pages)
                    records.extend(page_records)
                    if page_records:
                        print(f"  [{i+1}/{len(council_links)}] {council_name}: {len(page_records)} records")
                except Exception as e:
                    print(f"  [{i+1}] Error on {council_name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _scrape_council(self, url: str, council_name: str, seen_urls: set[str], visited_pages: set[str]) -> list[dict]:
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
            if "moj.go.jp" not in full_url:
                continue
            if full_url in visited_pages:
                continue
            is_sub = any(kw in text for kw in [
                "議事要旨", "議事録", "開催状況", "会議", "部会", "分科会",
                "小委員会", "ワーキング", "研究会",
            ])
            is_meeting_url = any(kw in href for kw in [
                "gijiyoushi", "gijiroku", "giji", "kaisai",
            ])
            if is_sub or is_meeting_url:
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
        records = []

        # Try links in sections (MOJ uses <a> tags separated by <br>)
        for a in soup.find_all("a", href=True):
            link_text = normalize(a.get_text())
            href = a["href"]

            if not link_text or len(link_text) < 5:
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

            # Date from link text
            meeting_date = parse_date(link_text)
            if not meeting_date:
                # Try parent element
                parent = a.find_parent(["li", "td", "dd", "p", "div"])
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
        if any(kw in text for kw in ["配布資料", "配付資料", "資料一覧", "資料", "会議用資料"]):
            return "material"
        if "答申" in text or "報告書" in text:
            return "material"
        # Meeting pages (第N回会議)
        if re.search(r"第\d+回", text) and "会議" in text:
            return "minutes"

        if any(kw in href for kw in ["gijiroku", "giji", "gijiyoushi"]):
            return "minutes"
        if "shiryou" in href or "siryou" in href:
            return "material"

        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = MOJScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
