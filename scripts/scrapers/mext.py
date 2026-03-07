"""Scraper for Ministry of Education, Culture, Sports, Science and Technology (文部科学省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class MEXTScraper(BaseScraper):
    ministry_slug = "mext"
    BASE_URL = "https://www.mext.go.jp"
    INDEX_URL = "https://www.mext.go.jp/b_menu/shingi/main_b5.htm"

    # Chousa hub pages list committees, not meetings.
    # Pattern: /b_menu/shingi/chousa/{category}/index.htm
    _HUB_RE = re.compile(r"/b_menu/shingi/chousa/[^/]+/index\.htm$")

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        print("  Fetching MEXT shingi master index...")
        try:
            soup = self.fetch(self.INDEX_URL)
        except Exception as e:
            print(f"  Fatal: cannot fetch index: {e}")
            return records

        # Phase 1: Categorize links from master index
        council_pages: list[tuple[str, str]] = []
        hub_pages: list[tuple[str, str]] = []
        seen_council: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if not text or len(text) < 2 or href.startswith("#"):
                continue
            full_url = urljoin(self.INDEX_URL, href)
            if "mext.go.jp" not in full_url or "/b_menu/shingi/" not in full_url:
                continue
            if full_url == self.INDEX_URL or full_url in seen_council:
                continue
            seen_council.add(full_url)

            if self._HUB_RE.search(full_url):
                hub_pages.append((full_url, text))
            else:
                council_pages.append((full_url, text))

        print(f"  Found {len(council_pages)} direct councils, {len(hub_pages)} hub pages")

        # Phase 2: Expand hub pages into individual committee pages
        for hub_url, hub_name in hub_pages:
            print(f"  Expanding hub: {hub_name}...")
            try:
                hub_soup = self.fetch(hub_url)
            except Exception as e:
                print(f"    Error: {e}")
                continue

            count = 0
            for a in hub_soup.find_all("a", href=True):
                href = a["href"]
                text = normalize(a.get_text())
                if not text or len(text) < 3 or href.startswith("#"):
                    continue
                full_url = urljoin(hub_url, href)
                if full_url in seen_council:
                    continue
                if "mext.go.jp" not in full_url:
                    continue
                if "/b_menu/shingi/" not in full_url:
                    continue
                # Skip other hub pages and the master index
                if self._HUB_RE.search(full_url) or "main_b5" in full_url:
                    continue
                seen_council.add(full_url)
                council_pages.append((full_url, text))
                count += 1

            if count:
                print(f"    -> {count} committees")

        print(f"  Total pages to process: {len(council_pages)}")

        # Phase 3: Scrape each council/committee page
        for i, (url, name) in enumerate(council_pages):
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
        """Scrape a council/committee page and follow sub-links."""
        if url in visited_pages:
            return []
        visited_pages.add(url)

        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        records.extend(self._extract_meetings(soup, url, council_name, seen_urls))

        # Follow sub-links one level deeper (meeting lists, sub-working-groups)
        sub_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())

            if not text or len(text) < 2:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue

            full_url = urljoin(url, href)

            if "mext.go.jp" not in full_url:
                continue
            if full_url in visited_pages:
                continue

            is_sub_council = any(kw in text for kw in [
                "議事要旨", "議事録", "開催状況", "会議", "部会", "分科会",
                "小委員会", "ワーキング", "研究会", "懇談会", "検討会",
                "一覧",
            ])
            is_meeting_list = any(kw in href for kw in [
                "gijiyoushi", "gijiroku", "giji_list", "kaisai",
            ])

            if is_sub_council or is_meeting_list:
                sub_name = council_name if any(kw in text for kw in ["議事", "開催", "一覧"]) else text
                sub_links.append((full_url, sub_name))

        for sub_url, sub_name in sub_links[:50]:
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
        """Extract meeting records from a page.

        Uses a single-pass approach: find all links matching doc_type keywords,
        then search the surrounding context (parent elements, preceding headings)
        for meeting dates.
        """
        records = []

        for a in soup.find_all("a", href=True):
            link_text = normalize(a.get_text())
            href = a["href"]

            if not link_text or len(link_text) < 2:
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            doc_type = self._detect_doc_type(link_text, href)
            if doc_type is None:
                continue

            meeting_date = self._find_meeting_date(a)

            seen_urls.add(full_url)
            title = f"{council_name} {link_text}" if council_name not in link_text else link_text

            records.append({
                "committee_name": council_name,
                "title": title,
                "url": full_url,
                "meeting_date": meeting_date,
                "doc_type": doc_type,
            })

        return records

    def _find_meeting_date(self, a_tag) -> str | None:
        """Find meeting date from context around a link."""
        # 1. Link text itself
        d = parse_date(normalize(a_tag.get_text()))
        if d:
            return d

        # 2. Immediate parent (<li>, <td>, <dd>)
        parent = a_tag.parent
        if parent:
            d = parse_date(normalize(parent.get_text()))
            if d:
                return d

        # 3. Grandparent (<tr>, <dl>) — only if text is short enough
        if parent and parent.parent:
            gp_text = normalize(parent.parent.get_text())
            if len(gp_text) < 500:
                d = parse_date(gp_text)
                if d:
                    return d

        # 4. Preceding heading (h2-h5, dt) for heading + list patterns
        prev = a_tag.find_previous(["h2", "h3", "h4", "h5", "dt"])
        if prev:
            d = parse_date(normalize(prev.get_text()))
            if d:
                return d

        return None

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
    scraper = MEXTScraper()
    try:
        records = scraper.scrape()
        if records:
            scraper.save_to_db(records)
    finally:
        scraper.close()
