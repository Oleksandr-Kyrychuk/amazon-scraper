# app/api/routes.py
from fastapi import APIRouter
from app.database import get_products

router = APIRouter()

@router.get("/api/products")
async def get_all_products():
    return get_products()