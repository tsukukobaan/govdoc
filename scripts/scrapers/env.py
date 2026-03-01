"""Scraper for Ministry of the Environment (環境省) advisory councils."""
import re
from urllib.parse import urljoin

from .base import BaseScraper, normalize, parse_date


class ENVScraper(BaseScraper):
    ministry_slug = "env"
    BASE_URL = "https://www.env.go.jp"
    COUNCIL_INDEX = "https://www.env.go.jp/council/"
    B_INFO_URL = "https://www.env.go.jp/council/b_info.html"
    SONOTA_URL = "https://www.env.go.jp/council/sonota.html"

    def scrape(self) -> list[dict]:
        records = []
        seen_urls: set[str] = set()

        # Collect all council meeting-list page URLs from both index pages
        council_pages = []
        for index_url, label in [
            (self.B_INFO_URL, "中央環境審議会"),
            (self.SONOTA_URL, "その他審議会"),
        ]:
            print(f"  Fetching ENV {label}...")
            try:
                soup = self.fetch(index_url)
                pages = self._collect_yoshi_links(soup, index_url)
                council_pages.extend(pages)
                print(f"    -> {len(pages)} council pages found")
            except Exception as e:
                print(f"    Error: {e}")

        print(f"  Total council pages to scrape: {len(council_pages)}")

        # Scrape each council meeting-list page
        for i, (url, name) in enumerate(council_pages):
            if i >= 100:  # Safety limit
                break
            try:
                page_records = self._scrape_meeting_list(url, name, seen_urls)
                records.extend(page_records)
                if page_records:
                    print(f"  [{i+1}/{len(council_pages)}] {name}: {len(page_records)} records")
            except Exception as e:
                print(f"  [{i+1}] Error on {name}: {e}")

        print(f"  Total records: {len(records)}")
        return records

    def _collect_yoshi_links(self, soup, base_url: str) -> list[tuple[str, str]]:
        """Collect links to yoshi*.html meeting-list pages."""
        pages = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize(a.get_text())
            # Match yoshi*.html pages (meeting list pages)
            if "yoshi" in href and href.endswith(".html"):
                full_url = urljoin(base_url, href)
                if full_url not in seen:
                    seen.add(full_url)
                    name = text if text else href.split("/")[-1]
                    pages.append((full_url, name))
        return pages

    def _scrape_meeting_list(self, url: str, council_name: str, seen_urls: set[str]) -> list[dict]:
        """Scrape a yoshi*.html page for individual meeting records."""
        records = []
        try:
            soup = self.fetch(url)
        except Exception:
            return records

        # Meeting entries are in <li> elements within <ul> lists
        # Format: 令和7年7月14日 総合政策部会（第121回） 議事次第・配付資料 ／ 議事録
        for li in soup.find_all("li"):
            li_text = normalize(li.get_text())
            if not li_text or len(li_text) < 10:
                continue

            # Try to extract date from the li text
            meeting_date = parse_date(li_text)

            # Find links within this li
            for a in li.find_all("a", href=True):
                link_text = normalize(a.get_text())
                href = a["href"]

                if not link_text or len(link_text) < 2:
                    continue

                full_url = urljoin(url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # Determine doc type
                doc_type = "minutes"
                if "議事録" in link_text:
                    doc_type = "minutes"
                elif "議事要旨" in link_text:
                    doc_type = "summary"
                elif "配付資料" in link_text or "議事次第" in link_text or "資料" in link_text:
                    doc_type = "material"
                elif "答申" in link_text or "報告" in link_text:
                    doc_type = "material"
                else:
                    # Skip non-document links (navigation, etc.)
                    continue

                # Extract committee name from li text if possible
                committee = council_name
                match = re.search(r"(.+?(?:部会|分科会|委員会|小委員会|専門委員会|ワーキング|WG))", li_text)
                if match:
                    name = match.group(1)
                    # Remove date prefix
                    name = re.sub(r"^.*?日\s*", "", name)
                    # Remove meeting number
                    name = re.sub(r"（第\d+回）", "", name).strip()
                    if name and len(name) > 2:
                        committee = name

                title = f"{committee} {link_text}" if committee not in link_text else link_text

                records.append({
                    "committee_name": committee,
                    "title": title,
                    "url": full_url,
                    "meeting_date": meeting_date,
                    "doc_type": doc_type,
                })

        return records


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper = ENVScraper()
    records = scraper.scrape()
    if records:
        scraper.save_to_db(records)
