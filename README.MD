# Amazon Product Scraper

A Python-based application that scrapes laptop product data from Amazon and provides a web interface to view and analyze the data.

## Features
- **Scraper**: Extracts product details (title, price, original price, rating, reviews, delivery, seller, URL) from Amazon using Selenium and BeautifulSoup.
- **Web Interface**: Built with FastAPI, displays products in a table with filters (min rating, max price, min reviews) and pagination.
- **Analytics**: Shows average price and reviews (rating ≥ 4.0), maximum discount, top 3 products by rating and price, and a price distribution chart.
- **Bonus Features**:
  - Docker support for easy deployment.
  - CSV export of product data.
  - REST API (`/api/products`).
  - SQLAlchemy ORM for database operations.
  - Task management (start, cancel, view scraping tasks).
  - Proxy support (optional).

## Project Structure
```
amazon-scraper/
├── app/
│   ├── api/                # API routes
│   ├── models/             # SQLAlchemy models
│   ├── scraper/            # Scraper logic
│   │   ├── amazon_scraper.py
│   │   ├── parsers.py      # Parsing functions
│   ├── templates/          # HTML templates
│   ├── tests/              # Unit tests
│   ├── analytics.py        # Analytics logic
│   ├── database.py         # Database operations
│   ├── main.py             # FastAPI application
├── Dockerfile              # Docker configuration
├── requirements.txt        # Python dependencies
├── scraper.py              # CLI entry point for scraper
├── amazon.db               # SQLite database
├── scraper.log             # Scraper logs
├── README.md               # This file
```

## Prerequisites
- Python 3.9+
- Docker (optional, for containerized deployment)
- Google Chrome (for Selenium)

## Setup Instructions

### Local Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd amazon-scraper
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the scraper via CLI:
   ```bash
   python scraper.py --query "laptop" --pages 1 --db amazon.db --headless False
   ```
4. Run the FastAPI application:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
5. Open `http://localhost:8000` in your browser to access the web interface.

### Docker Setup
1. Build the Docker image:
   ```bash
   docker build -t amazon-scraper .
   ```
2. Run the container:
   ```bash
   docker run -p 8000:8000 -v $(pwd)/amazon.db:/app/amazon.db amazon-scraper
   ```
3. Access the web interface at `http://localhost:8000`.

## Usage Examples
- **Start scraping**:
  - Via CLI: `python scraper.py --query "laptop" --pages 2 --db amazon.db`
  - Via web interface: Enter query and pages in the form at `http://localhost:8000`.
- **View analytics**: Navigate to `http://localhost:8000/analytics`.
- **Export data**: Click "Export to CSV" on the main page.
- **Filter products**: Use the filter form to set minimum rating, maximum price, or minimum reviews.
- **API**: Get products via:
  ```bash
  curl http://localhost:8000/api/products?min_rating=4.0
  ```
- **Proxy (optional)**: Run with a proxy:
  ```bash
  python scraper.py --query "laptop" --pages 1 --proxy "http://your_proxy:port"
  ```

## Testing
Run unit tests:
```bash
pytest app/tests/
```

## Notes
- The scraper includes delays and human-like behavior (mouse movements, scrolling) to avoid detection by Amazon.
- CAPTCHA handling requires manual intervention in non-headless mode. Proxy support can improve reliability.
- Logs are saved to `scraper.log` for debugging.
- The SQLite database (`amazon.db`) is mounted as a volume in Docker to persist data.