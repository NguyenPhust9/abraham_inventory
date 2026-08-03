from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv(override=True)
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT code, stock, reserved, updated_at "
            "FROM products "
            "WHERE code ILIKE :pattern"
        ),
        {"pattern": "%24BIKE%Cam%"},
    )
    rows = result.mappings().all()

    if not rows:
        print("KHONG TIM THAY SAN PHAM NAO KHOP.")
    else:
        for row in rows:
            print(dict(row))