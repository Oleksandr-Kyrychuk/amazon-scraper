from sqlalchemy import create_engine, text
import logging
import pandas as pd
import sqlite3
from collections import namedtuple
import os

# Налаштування логування
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)


def init_db(db_path="amazon.db"):
    """Ініціалізує базу даних і створює таблицю products, якщо вона не існує."""
    try:
        # Перетворення на абсолютний шлях
        db_path = os.path.abspath(db_path)
        logging.info(f"Ініціалізація бази даних: {db_path}")

        # Перевірка існування директорії
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as connection:
            # Перевірка, чи таблиця існує
            result = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")).fetchone()
            if not result:
                logging.info("Таблиця 'products' не існує, створюємо...")
                connection.execute(text("""
                    CREATE TABLE products (
                        asin TEXT PRIMARY KEY,
                        title TEXT,
                        price REAL,
                        original_price REAL,
                        rating REAL,
                        reviews INTEGER,
                        delivery TEXT,
                        seller TEXT,
                        url TEXT
                    )
                """))
                connection.commit()
                logging.info("Таблиця 'products' успішно створена")
            else:
                logging.debug("Таблиця 'products' уже існує")
        logging.info(f"База даних ініціалізована: {db_path}")
        return db_path
    except Exception as e:
        logging.error(f"Помилка ініціалізації бази даних {db_path}: {e}")
        raise


def save_to_db(product_data, db_path="amazon.db"):
    """Зберігає дані продукту в базу даних."""
    try:
        db_path = init_db(db_path)  # Ініціалізація перед збереженням
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as connection:
            product_data = {
                "asin": product_data.get("asin", ""),
                "title": product_data.get("title", "N/A")[:255],
                "price": float(product_data.get("price", 0.0)) or 0.0,
                "original_price": float(product_data.get("original_price", 0.0)) or 0.0,
                "rating": float(product_data.get("rating", 0.0)) or 0.0,
                "reviews": int(product_data.get("reviews", 0)) or 0,
                "delivery": product_data.get("delivery", "N/A")[:255],
                "seller": product_data.get("seller", "N/A")[:255],
                "url": product_data.get("url", "N/A")[:1024]
            }
            connection.execute(
                text("""
                    INSERT OR REPLACE INTO products (
                        asin, title, price, original_price, rating, reviews, delivery, seller, url
                    ) VALUES (
                        :asin, :title, :price, :original_price, :rating, :reviews, :delivery, :seller, :url
                    )
                """), product_data
            )
            connection.commit()
        logging.debug(f"Збережено продукт в базу даних: {product_data['asin']}")
    except Exception as e:
        logging.error(f"Помилка збереження в базу даних {db_path}: {e}")
        raise


def get_products(db_path="amazon.db", min_rating=None, max_price=None, min_reviews=None):
    """Отримує продукти з бази даних із застосуванням фільтрів."""
    try:
        db_path = init_db(db_path)  # Ініціалізація перед запитом
        engine = create_engine(f"sqlite:///{db_path}")
        query = "SELECT * FROM products WHERE 1=1"
        params = {}
        if min_rating is not None:
            if min_rating < 0:
                raise ValueError("Мінімальний рейтинг не може бути від’ємним")
            query += " AND rating >= :min_rating"
            params["min_rating"] = min_rating
        if max_price is not None:
            if max_price < 0:
                raise ValueError("Максимальна ціна не може бути від’ємною")
            query += " AND price <= :max_price"
            params["max_price"] = max_price
        if min_reviews is not None:
            if min_reviews < 0:
                raise ValueError("Мінімальна кількість відгуків не може бути від’ємною")
            query += " AND reviews >= :min_reviews"
            params["min_reviews"] = min_reviews

        with engine.connect() as connection:
            result = connection.execute(text(query), params).fetchall()
            Product = namedtuple("Product",
                                 ["asin", "title", "price", "original_price", "rating", "reviews", "delivery", "seller",
                                  "url"])
            logging.debug(f"Отримано {len(result)} продуктів з бази даних")
            return [Product(*row) for row in result]
    except Exception as e:
        logging.error(f"Помилка отримання продуктів з {db_path}: {e}")
        return []


def export_to_csv(products, db_path="amazon.db"):
    """Експортує продукти в CSV-файл."""
    try:
        if not products:
            logging.warning("Немає продуктів для експорту")
            return None
        df = pd.DataFrame([{
            "asin": p.asin,
            "title": p.title,
            "price": p.price,
            "original_price": p.original_price,
            "rating": p.rating,
            "reviews": p.reviews,
            "delivery": p.delivery,
            "seller": p.seller,
            "url": p.url
        } for p in products])
        csv_file = "products_export.csv"
        df.to_csv(csv_file, index=False, encoding="utf-8")
        logging.info(f"Дані експортовано до {csv_file}")
        return csv_file
    except Exception as e:
        logging.error(f"Помилка експорту в CSV: {e}")
        return None


def clear_db(db_path="amazon.db"):
    """Очищає таблицю products у базі даних."""
    try:
        db_path = init_db(db_path)  # Ініціалізація перед очищенням
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("DELETE FROM products")
        conn.commit()
        conn.close()
        logging.info(f"База даних {db_path} очищена")
    except Exception as e:
        logging.error(f"Помилка очищення бази даних {db_path}: {e}")
        raise