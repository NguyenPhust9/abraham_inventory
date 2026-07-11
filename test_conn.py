import psycopg2 # type: ignore

try:
    conn = psycopg2.connect(
        "postgresql://neondb_owner:npg_as8Fj2dLYfop@ep-gentle-field-atbthxx6.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require",
        connect_timeout=10
    )
    print("Kết nối thành công!")
    conn.close()
except Exception as e:
    print("Lỗi kết nối:", e)