"""Run all ministry scrapers to update the database."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scrapers.cao import CAOScraper
from scrapers.cas import CASScraper
from scrapers.env import ENVScraper
from scrapers.fsa import FSAScraper
from scrapers.kantei import KANTEIScraper
from scrapers.maff import MAFFScraper
from scrapers.meti import METIScraper
from scrapers.mext import MEXTScraper
from scrapers.mhlw import MHLWScraper
from scrapers.mlit import MLITScraper
from scrapers.mod import MODScraper
from scrapers.mof import MOFScraper
from scrapers.soumu import SOUMUScraper


def main():
    scrapers = [
        ("内閣官房", CASScraper),
        ("内閣府", CAOScraper),
        ("金融庁", FSAScraper),
        ("財務省", MOFScraper),
        ("文部科学省", MEXTScraper),
        ("厚生労働省", MHLWScraper),
        ("経済産業省", METIScraper),
        ("国土交通省", MLITScraper),
        ("環境省", ENVScraper),
        ("防衛省", MODScraper),
        ("農林水産省", MAFFScraper),
        ("総務省", SOUMUScraper),
        ("首相官邸", KANTEIScraper),
    ]

    for name, cls in scrapers:
        print(f"\n{'='*60}")
        print(f"Scraping: {name}")
        print(f"{'='*60}")
        scraper = cls()
        try:
            records = scraper.scrape()
            if records:
                scraper.save_to_db(records)
            else:
                print("  No records found")
        except Exception as e:
            print(f"  FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            scraper.close()


if __name__ == "__main__":
    main()
