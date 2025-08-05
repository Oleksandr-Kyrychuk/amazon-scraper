import asyncio
import uuid
from fastapi import FastAPI, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.database import get_products, clear_db, init_db
from app.scraper.amazon_scraper import AmazonScraper
from app.analytics import get_analytics
import pandas as pd
import io
import logging
import os

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
scrape_tasks = {}
scrape_tasks_lock = asyncio.Lock()

# Налаштування логування
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)

# Ініціалізація бази даних при запуску програми
init_db()


class ScrapeRequest(BaseModel):
    query: str
    pages: int
    headless: bool = True


async def run_scraper(scraper, task_id):
    try:
        await asyncio.to_thread(scraper.run, task_id)
        async with scrape_tasks_lock:
            scrape_tasks[task_id]["status"] = "completed"
            scrape_tasks[task_id]["message"] = f"Скрапінг завершено: зібрано {scraper.total_products} продуктів"
    except Exception as e:
        logging.error(f"Помилка в run_scraper (task_id={task_id}): {e}")
        async with scrape_tasks_lock:
            scrape_tasks[task_id]["status"] = "failed"
            scrape_tasks[task_id]["message"] = f"Помилка скрапінгу: {str(e)}"
    finally:
        async with scrape_tasks_lock:
            if task_id in scrape_tasks:
                scraper.cancel()
                scrape_tasks[task_id]["scraper"] = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, min_rating: float = None, max_price: float = None, min_reviews: int = None,
                message: str = None, page: int = 1, per_page: int = 10):
    try:
        # Конвертуємо параметри, якщо вони передані як рядки "None"
        min_rating = float(min_rating) if min_rating is not None and min_rating != "None" else None
        max_price = float(max_price) if max_price is not None and max_price != "None" else None
        min_reviews = int(min_reviews) if min_reviews is not None and min_reviews != "None" else None

        products = get_products(min_rating=min_rating, max_price=max_price, min_reviews=min_reviews)
        total_products = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]
    except Exception as e:
        logging.error(f"Помилка при отриманні продуктів: {e}")
        paginated_products = []
        total_products = 0
    async with scrape_tasks_lock:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "products": paginated_products,
                "scrape_tasks": scrape_tasks,
                "min_rating": min_rating,
                "max_price": max_price,
                "min_reviews": min_reviews,
                "message": message or "База даних порожня або ще не створена. Почніть скрапінг.",
                "current_page": page,
                "total_pages": (total_products + per_page - 1) // per_page
            }
        )


@app.post("/scrape", response_class=RedirectResponse)
async def start_scrape(query: str = Form(...), pages: int = Form(...), headless: bool = Form(True)):
    if pages < 1:
        raise HTTPException(status_code=400, detail="Кількість сторінок має бути більшою за 0")

    task_id = str(uuid.uuid4())
    scraper = AmazonScraper(query=query, pages=pages, headless=headless)

    async with scrape_tasks_lock:
        scrape_tasks[task_id] = {
            "query": query,
            "pages": pages,
            "status": "running",
            "current_page": 0,
            "total_products": 0,
            "message": "Скрапінг розпочато",
            "scraper": scraper
        }

    asyncio.create_task(run_scraper(scraper, task_id))

    return RedirectResponse(
        url=f"/?message=Скрапінг розпочато для запиту '{query}' (ID: {task_id})",
        status_code=303
    )


@app.post("/scrape/cancel/{task_id}")
async def cancel_scrape(task_id: str):
    async with scrape_tasks_lock:
        if task_id not in scrape_tasks:
            raise HTTPException(status_code=404, detail="Задача не знайдена")
        if scrape_tasks[task_id]["status"] != "running":
            raise HTTPException(status_code=400, detail="Задача не виконується")

        scraper = scrape_tasks[task_id]["scraper"]
        scraper.cancel()
        scrape_tasks[task_id]["status"] = "cancelled"
        scrape_tasks[task_id]["message"] = "Скрапінг скасовано"
        scrape_tasks[task_id]["scraper"] = None
        return {"message": f"Скрапінг (ID: {task_id}) скасовано"}


@app.get("/scrape/all")
async def get_scrape_tasks():
    async with scrape_tasks_lock:
        tasks_for_response = {}
        for task_id, task in scrape_tasks.items():
            task_copy = task.copy()
            task_copy.pop("scraper", None)
            tasks_for_response[task_id] = task_copy
        return tasks_for_response


@app.post("/clear_db")
async def clear_database():
    try:
        clear_db()
        return {"success": True, "message": "База даних очищена"}
    except Exception as e:
        logging.error(f"Помилка очищення бази даних: {e}")
        return {"success": False, "error": str(e)}


@app.get("/export")
async def export_csv():
    try:
        products = get_products()
        df = pd.DataFrame(products)
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        return StreamingResponse(
            io.BytesIO(stream.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=products.csv"}
        )
    except Exception as e:
        logging.error(f"Помилка експорту CSV: {e}")
        raise HTTPException(status_code=500, detail="Помилка експорту даних")


@app.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request):
    try:
        analytics_data = get_analytics()
        return templates.TemplateResponse("analytics.html", {"request": request, "analytics": analytics_data})
    except Exception as e:
        logging.error(f"Помилка отримання аналітики: {e}")
        analytics_data = {
            "avg_price": 0.0,
            "max_discount": 0.0,
            "max_discount_product": None,
            "top_by_rating": [],
            "top_by_price": [],
            "price_distribution": {"labels": [], "values": []}
        }
        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "analytics": analytics_data,
            "error": "Помилка завантаження аналітики"
        })


@app.get("/favicon.ico")
async def favicon():
    favicon_path = "app/static/favicon.ico"
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    logging.debug("Файл favicon.ico не знайдено, повертаємо порожню відповідь")
    return Response(status_code=204)