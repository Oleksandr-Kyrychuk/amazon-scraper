import argparse
from app.scraper.amazon_scraper import AmazonScraper

def main():
    parser = argparse.ArgumentParser(description="Amazon Product Scraper")
    parser.add_argument("--query", default="laptop", help="Search query")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages to scrape")
    parser.add_argument("--db", default="amazon.db", help="Database file")
    args = parser.parse_args()

    if args.pages < 1:
        raise ValueError("Number of pages must be greater than 0")

    scraper = AmazonScraper(args.query, args.pages, args.db)
    scraper.run()

if __name__ == "__main__":
    main()