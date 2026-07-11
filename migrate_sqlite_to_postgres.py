import os
from datetime import datetime

from sqlalchemy import create_engine, select # type: ignore
from sqlalchemy.orm import sessionmaker # type: ignore

from app import Base, Product, DB_PATH


def main():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for migration.")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    sqlite_engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    sqlite_session = sessionmaker(bind=sqlite_engine)()

    postgres_engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
    postgres_session = sessionmaker(bind=postgres_engine)()

    try:
        Base.metadata.create_all(postgres_engine)

        products = sqlite_session.execute(select(Product)).scalars().all()
        total_sqlite = len(products)
        added = 0
        updated = 0

        for item in products:
            existing = postgres_session.query(Product).filter_by(code=item.code).first()
            if existing:
                existing.model = item.model
                existing.color = item.color
                existing.category = item.category
                existing.unit = item.unit
                existing.stock = item.stock
                existing.reserved = item.reserved
                existing.price = item.price
                existing.image_filename = item.image_filename
                existing.updated_at = item.updated_at or datetime.utcnow()
                updated += 1
            else:
                new_product = Product(
                    code=item.code,
                    model=item.model,
                    color=item.color,
                    category=item.category,
                    unit=item.unit,
                    stock=item.stock,
                    reserved=item.reserved,
                    price=item.price,
                    image_filename=item.image_filename,
                    updated_at=item.updated_at or datetime.utcnow(),
                )
                postgres_session.add(new_product)
                added += 1

        postgres_session.commit()
        print("Đã chuyển xong dữ liệu")
        print(f"Thêm mới: {added}")
        print(f"Cập nhật: {updated}")
        print(f"Tổng sản phẩm SQLite: {total_sqlite}")
    finally:
        sqlite_session.close()
        postgres_session.close()


if __name__ == "__main__":
    main()
