# app/tests/test_scraper.py
import unittest
from bs4 import BeautifulSoup
from app.scraper.amazon_scraper import get_title_from_soup, get_price_from_soup, get_rating_from_soup

class TestScraper(unittest.TestCase):
    def test_extract_product_data(self):
        html = """
        <div class="s-result-item">
            <h2><a><span>Test Laptop</span></a></h2>
            <div class="a-price"><span class="a-offscreen">$999.99</span></div>
            <div class="a-icon-star-small"><span class="a-icon-alt">4.5 out of 5 stars</span></div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(get_title_from_soup(soup), "Test Laptop")
        self.assertEqual(get_price_from_soup(soup), 999.99)
        self.assertEqual(get_rating_from_soup(soup), 4.5)

if __name__ == "__main__":
    unittest.main()