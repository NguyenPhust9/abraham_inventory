# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env", override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise SystemExit("Thieu DATABASE_URL trong .env")

# In ra (che password) de kiem tra dinh dang truoc khi ket noi
safe_url = DATABASE_URL
if "@" in safe_url and "://" in safe_url:
    scheme, rest = safe_url.split("://", 1)
    if "@" in rest:
        creds, host_part = rest.rsplit("@", 1)
        if ":" in creds:
            user, _pwd = creds.split(":", 1)
            safe_url = f"{scheme}://{user}:***@{host_part}"

print("DATABASE_URL (che password):", safe_url)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1")).scalar()
    print("Ket noi Supabase thanh cong. Kiem tra SELECT 1 =", result)

    count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
    print("So dong trong bang products:", count)