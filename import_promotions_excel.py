import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import psycopg2
from sqlalchemy.engine import make_url


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_ALIASES = {
    "gt100": "GT100 Nhôm 700C",
    "fhuang 24 kèm rổ và cây bắt rổ": "FHUANG 24 Kèm rỗ và cây bắt rỗ",
}


def load_local_env():
    for filename in (".env.pooler", ".env.local", ".env"):
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    pooler_host = os.environ.get("SUPABASE_POOLER_HOST", "").strip()
    if pooler_host:
        parsed = make_url(url)
        username = parsed.username
        direct_host = parsed.host or ""
        if direct_host.startswith("db.") and direct_host.endswith(".supabase.co"):
            project_ref = direct_host.split(".")[1]
            if username == "postgres":
                username = f"postgres.{project_ref}"
        url = parsed.set(
            host=pooler_host,
            port=int(os.environ.get("SUPABASE_POOLER_PORT", "5432")),
            username=username,
        ).render_as_string(hide_password=False)
    return url


def find_column(columns, *names):
    normalized = {str(column).strip().casefold(): column for column in columns}
    for name in names:
        if name.casefold() in normalized:
            return normalized[name.casefold()]
    return None


def parse_date(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
        except (TypeError, ValueError, OverflowError):
            return None
    text_value = str(value).strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text_value, date_format).date()
        except ValueError:
            continue
    return None


def main(path):
    print("Đang đọc cấu hình...", flush=True)
    load_local_env()
    print("Đang đọc file Excel...", flush=True)
    frame = pd.read_excel(path, dtype=object)
    code_col = find_column(frame.columns, "Mã hàng", "Mã hàng hóa", "Mã sản phẩm", "code")
    price_col = find_column(frame.columns, "Giá khuyến mãi", "Giá KM", "Giá giảm")
    tag_col = find_column(frame.columns, "Tag", "Tag hiển thị", "Nhãn")
    start_col = find_column(frame.columns, "Áp dụng từ", "Từ ngày", "Ngày bắt đầu")
    end_col = find_column(frame.columns, "Áp dụng tới", "Đến ngày", "Ngày kết thúc")
    if not all((code_col, price_col, start_col, end_col)):
        raise ValueError("File thiếu một trong các cột: Mã hàng, Giá khuyến mãi, Áp dụng từ, Áp dụng tới")

    prepared = []
    errors = []
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        code = str(row[code_col]).strip() if not pd.isna(row[code_col]) else ""
        lookup_code = MODEL_ALIASES.get(code.casefold(), code)
        try:
            price = float(row[price_col])
        except (TypeError, ValueError):
            price = 0
        start_date = parse_date(row[start_col])
        end_date = parse_date(row[end_col])
        raw_tag = str(row[tag_col]).strip().casefold() if tag_col and not pd.isna(row[tag_col]) else "discount"
        tag = "hot" if raw_tag in {"hot", "nóng"} else "discount"
        if not code or price <= 0 or not start_date or not end_date or end_date < start_date:
            errors.append(f"Dòng {row_number}: dữ liệu không hợp lệ")
            continue
        prepared.append((price, tag, start_date, end_date, lookup_code, code))

    print(f"Đã đọc {len(prepared)} dòng hợp lệ. Đang kết nối database...", flush=True)
    connection = psycopg2.connect(database_url())
    print("Đã kết nối. Đang cập nhật dữ liệu...", flush=True)
    try:
        with connection.cursor() as cursor:
            updated = 0
            imported_rows = 0
            missing = []
            for values in prepared:
                update_values = values[:4] + (values[4],)
                cursor.execute(
                    """
                    UPDATE products
                    SET promotion_price=%s, promotion_tag=%s,
                        promotion_start=%s, promotion_end=%s
                    WHERE lower(model)=lower(%s)
                    """,
                    update_values,
                )
                matched = cursor.rowcount
                if not matched:
                    cursor.execute(
                        """
                        UPDATE products
                        SET promotion_price=%s, promotion_tag=%s,
                            promotion_start=%s, promotion_end=%s
                        WHERE lower(code)=lower(%s)
                        """,
                        update_values,
                    )
                    matched = cursor.rowcount
                if matched:
                    imported_rows += 1
                    updated += matched
                    continue
                missing.append(values[-1])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"Đã import: {imported_rows} dòng cho {updated} biến thể sản phẩm")
    print(f"Không tìm thấy: {len(missing)} mã")
    if missing:
        print("Danh sách không tìm thấy: " + ", ".join(missing))
    print(f"Dòng dữ liệu lỗi: {len(errors)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Cách dùng: python import_promotions_excel.py <file.xlsx>")
    main(sys.argv[1])
