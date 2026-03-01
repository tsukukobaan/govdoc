"""Run all ministry scrapers to update the database."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrapers.env import ENVScraper
from scrapers.fsa import FSAScraper
from scrapers.maff import MAFFScraper
from scrapers.mhlw import MHLWScraper
from scrapers.meti import METIScraper
from scrapers.mlit import MLITScraper
from scrapers.soumu import SOUMUScraper


def main():
    scrapers = [
        ("金融庁", FSAScraper),
        ("厚生労働省", MHLWScraper),
        ("経済産業省", METIScraper),
        ("環境省", ENVScraper),
        ("国土交通省", MLITScraper),
        ("総務省", SOUMUScraper),
        ("農林水産省", MAFFScraper),
    ]

    for name, cls in scrapers:
        print(f"\n{'='*60}")
        print(f"Scraping: {name}")
        print(f"{'='*60}")
        try:
            scraper = cls()
            records = scraper.scrape()
            if records:
                scraper.save_to_db(records)
            else:
                print("  No records found")
        except Exception as e:
            print(f"  FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
