# app/models/product.py
from sqlalchemy import Column, String, Float, Integer
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    asin = Column(String, primary_key=True)  # Use asin as primary key
    title = Column(String)
    price = Column(Float)
    original_price = Column(Float)
    rating = Column(Float)
    reviews = Column(Integer)
    delivery = Column(String)
    seller = Column(String)
    url = Column(String)