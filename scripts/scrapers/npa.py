"""Scraper for National Police Agency (警察庁) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class NPAScraper(BaseScraper):
    ministry_slug = "npa"

    # NPA councils are spread across different bureau paths
    INDEX_URLS = [
        ("https://www.npa.go.jp/policies/council/index.html", None),
        ("https://www.npa.go.jp/bureau/traffic/council/index.html", None),
    ]

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        for index_url, default_name in self.INDEX_URLS:
            print(f"  Fetching NPA index: {index_url}")
            try:
                soup = self.fetch(index_url)
            except Exception as e:
                print(f"  Error fetching {index_url}: {e}")
                continue

            # Extract meetings directly from this page (NPA often has inline docs)
            page_records = self._extract_meetings(soup, index_url, default_name or "警察庁審議会", seen_urls)
            records.extend(page_records)
            if page_records:
                print(f"    Inline records: {len(page_records)}")

            # Follow council links
            council_links = self._find_council_links(soup, index_url, visited_pages)
            print(f"  Found {len(council_links)} council links")

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

    def _find_council_links(self, soup, base_url: str, visited_pages: set[str]) -> list[tuple[str, str]]:
        council_links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            if not text or len(text) < 3:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            full_url = urljoin(base_url, href)
            if "npa.go.jp" not in full_url:
                continue
            if full_url in seen or full_url in visited_pages or full_url == base_url:
                continue
            # Follow council/committee pages
            if any(kw in text for kw in [
                "審議会", "研究会", "検討会", "委員会", "対策会議",
                "懇談会", "ワーキング", "有識者",
            ]) or any(kw in href for kw in [
                "council", "kenkyuukai", "kentou", "kaigi",
            ]):
                seen.add(full_url)
                council_links.append((full_url, text))
        return council_links

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
            if "npa.go.jp" not in full_url:
                continue
            if full_url in visited_pages:
                continue
            is_sub = any(kw in text for kw in [
                "議事要旨", "議事録", "議事概要", "開催状況", "部会",
                "検討会", "研究会",
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

        # NPA traffic council pages have meetings inline with documents
        # Try table-based structure
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
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

        # Try list-based structure
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
                title = f"{council_name} {link_text}" if council_name not in link_text else link_text
                records.append({
                    "committee_name": council_name,
                    "title": title,
                    "url": full_url,
                    "meeting_date": meeting_date or parse_date(li_text),
                    "doc_type": doc_type,
                })

        # Also extract from plain <a> tags with meeting patterns (第N回)
        for a in soup.find_all("a", href=True):
            link_text = normalize(a.get_text())
            href = a["href"]
            if not link_text or len(link_text) < 5:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            # Only match meeting-like links not already caught
            if not re.search(r"第\d+回", link_text):
                continue
            doc_type = self._detect_doc_type(link_text, href)
            if doc_type is None:
                # Meeting page links (第N回) default to minutes
                if "会議" in link_text or "開催" in link_text:
                    doc_type = "minutes"
                else:
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
        if any(kw in text for kw in ["議事次第", "次第"]):
            return "material"
        if "答申" in text or "報告書" in text or "提言" in text:
            return "material"

        if any(kw in href for kw in ["gijiroku", "giji", "gijiyoushi", "gijigaiyou"]):
            return "minutes"
        if "shiryou" in href or "siryou" in href:
            return "material"

        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = NPAScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
