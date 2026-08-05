"""
Script don dep gia tri NaN/Infinity trong cot price cua bang products.

Ban 3: them load_dotenv() de doc dung DATABASE_URL tu file .env,
tranh truong hop script tu roi ve dung SQLite local trong khi app
that dang dung Postgres (Supabase) -> dan den don nham database rong.

Duyet tung dong bang Python va kiem tra bang math.isnan/isinf, dang
tin cay hon cach so sanh "price != price" trong SQL (SQLite co the
xu ly so sanh NaN khong nhat quan).

Cach chay:
    py fix_nan_price.py
"""
import os
import math
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shop.db")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}")

Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    model = Column(String, nullable=False)
    color = Column(String, default="")
    category = Column(String, default="")
    unit = Column(String, default="Chiếc")
    stock = Column(Integer, default=0)
    reserved = Column(Integer, default=0)
    price = Column(Float, nullable=True)
    image_filename = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


SessionLocal = sessionmaker(bind=engine)
print(f"[SCRIPT DEBUG] Đang dùng DB: {engine.url}")

db = SessionLocal()
try:
    all_products = db.query(Product).all()

    bad_ids = []

    for p in all_products:
        if p.price is not None:
            try:
                if math.isnan(p.price) or math.isinf(p.price):
                    bad_ids.append(p.id)
            except TypeError:
                # gia tri khong phai so hop le, cung coi la loi
                bad_ids.append(p.id)

    print(f"Tim thay {len(bad_ids)} sản phẩm có giá không hợp lệ (NaN/Infinity).")

    if bad_ids:
        for pid in bad_ids:
            p = db.query(Product).get(pid)
            print(f"  - Mã hàng: {p.code} | Giá lỗi: {p.price!r} -> chuyển về NULL")
            p.price = None

        db.commit()
        print(f"Đã sửa xong {len(bad_ids)} sản phẩm.")
    else:
        print("Không có giá trị NaN/Infinity nào trong database.")

finally:
    db.close()