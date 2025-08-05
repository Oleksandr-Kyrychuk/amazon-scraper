from app.database import get_products
import numpy as np
import logging

def get_analytics(db_path="amazon.db"):
    products = get_products(db_path)
    if not products:
        return {
            "avg_price": 0.0,
            "avg_reviews": 0,
            "max_discount": 0.0,
            "max_discount_product": None,
            "top_by_rating": [],
            "top_by_price": [],
            "price_distribution": {"labels": [], "values": []}
        }

    high_rated = [p for p in products if p.rating >= 4.0]
    avg_price = sum(p.price for p in high_rated) / len(high_rated) if high_rated else 0.0
    avg_reviews = sum(p.reviews for p in high_rated) / len(high_rated) if high_rated else 0

    discounts = [p.original_price - p.price for p in products if p.original_price > p.price]
    max_discount = max(discounts) if discounts else 0.0
    max_discount_product = next((p for p in products if p.original_price - p.price == max_discount), None)

    top_by_rating = sorted(products, key=lambda x: x.rating, reverse=True)[:3]
    top_by_price = sorted(products, key=lambda x: x.price)[:3]

    prices = [p.price for p in products if p.price > 0]
    if prices:
        hist, bin_edges = np.histogram(prices, bins=10)
        price_distribution = {
            "labels": [f"${int(bin_edges[i])}-${int(bin_edges[i + 1])}" for i in range(len(bin_edges) - 1)],
            "values": hist.tolist()
        }
    else:
        price_distribution = {"labels": [], "values": []}

    # Конвертуємо Product у словники для серіалізації
    max_discount_product_dict = max_discount_product._asdict() if max_discount_product else None
    top_by_rating_dicts = [p._asdict() for p in top_by_rating]
    top_by_price_dicts = [p._asdict() for p in top_by_price]

    return {
        "avg_price": round(avg_price, 2),
        "avg_reviews": round(avg_reviews, 0),
        "max_discount": round(max_discount, 2),
        "max_discount_product": max_discount_product_dict,
        "top_by_rating": top_by_rating_dicts,
        "top_by_price": top_by_price_dicts,
        "price_distribution": price_distribution
    }