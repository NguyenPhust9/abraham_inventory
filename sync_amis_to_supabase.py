import json
import os
import re
import sys
import uuid
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv(override=True)
API_BASE = os.getenv(
    "AMIS_API_BASE",
    "https://crmconnect.misa.vn/api/v2",
).rstrip("/")

CLIENT_ID = os.getenv("AMIS_CLIENT_ID")
CLIENT_SECRET = os.getenv("AMIS_CLIENT_SECRET")
STOCK_CODE = os.getenv("AMIS_STOCK_CODE", "HCM 3").strip()
DATABASE_URL = os.getenv("DATABASE_URL")

# API noi bo ma man hinh "Tra cuu ton kho theo lo" cua AMIS su dung.
# Token nay la token phien dang nhap, khong dung chung voi AMIS_CLIENT_SECRET.
AMIS_APP_API_BASE = os.getenv(
    "AMIS_APP_API_BASE",
    "https://amisapp.misa.vn/crm/g1/api/business",
).rstrip("/")
AMIS_APP_TOKEN = os.getenv("AMIS_APP_TOKEN", "").strip()
AMIS_COMPANY_CODE = os.getenv("AMIS_COMPANY_CODE", "").strip()
AMIS_BATCH_STOCK_ID = os.getenv("AMIS_BATCH_STOCK_ID", "").strip()
AMIS_BATCH_ONLY = os.getenv("AMIS_BATCH_ONLY", "").strip().casefold() in {
    "1", "true", "yes", "on",
}

BATCH_COLUMNS = (
    "U2VxSUQsU3RvY2tJRFRleHQsUHJvZHVjdENvZGUsUHJvZHVjdE5hbWUs"
    "UHJvZHVjdENhdGVnb3J5SURUZXh0LENvbnZlcnNpb25Vbml0SURUZXh0"
    "LEJhdGNoTnVtYmVyLEV4cGlyeURhdGUsU3RvY2tRdWFudGl0eVN1bW1h"
    "cnksRXhpc3RBbW91bnQsRm9ybUxheW91dElELEZvcm1MYXlvdXRJRFRl"
    "eHQsT3duZXJJRCxPd25lcklEVGV4dA=="
)


def stop(message: str) -> None:
    print(f"\nLOI: {message}")
    sys.exit(1)


def parse_json_response(
    response: requests.Response,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        stop(
            f"API khong tra JSON. HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    if not isinstance(payload, dict):
        stop("Du lieu API tra ve khong dung dinh dang.")

    return payload


def decode_data(payload: dict[str, Any]) -> Any:
    data = payload.get("data")

    if data is None:
        data = payload.get("Data")

    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    return data


def extract_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    if isinstance(data, dict):
        for key in (
            "data",
            "Data",
            "items",
            "Items",
            "records",
            "Records",
            "result",
            "Result",
        ):
            value = data.get(key)

            if isinstance(value, list):
                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

    return []


def normalize_code(value: Any) -> str:
    return " ".join(
        str(value or "").strip().split()
    ).casefold()


def first_text(item: dict[str, Any], *keys: str) -> str:
    """Lay gia tri text dau tien, khong phan biet kieu viet ten truong."""
    normalized_items = {
        re.sub(r"[^a-z0-9]", "", str(key).casefold()): value
        for key, value in item.items()
    }

    for key in keys:
        value = item.get(key)

        if value is None:
            value = normalized_items.get(
                re.sub(r"[^a-z0-9]", "", key.casefold())
            )

        text_value = str(value or "").strip()

        if text_value:
            return " ".join(text_value.split())

    return ""


def split_model_color(value: str) -> tuple[str, str]:
    """Tach ten/mau tu dang 'PASSION 20 - CAM'."""
    text_value = " ".join(str(value or "").strip().split())
    parts = re.split(r"\s+-\s+", text_value)

    if len(parts) >= 2 and parts[-1].strip():
        return " - ".join(parts[:-1]).strip(), parts[-1].strip()

    return text_value, ""


def to_integer(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def parse_datetime(value: Any) -> datetime | None:
    text_value = str(value or "").strip()

    if not text_value:
        return None

    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None

def find_access_token(value: Any) -> str | None:
    """Tìm access token trong nhiều cấu trúc phản hồi AMIS khác nhau."""

    if isinstance(value, dict):
        # Kiểm tra các trường có tên giống access_token
        for key, child_value in value.items():
            normalized_key = (
                str(key)
                .strip()
                .lower()
                .replace("_", "")
                .replace("-", "")
            )

            if normalized_key in {
                "accesstoken",
                "token",
                "bearertoken",
                "authorizationtoken",
            }:
                if isinstance(child_value, str) and child_value.strip():
                    return child_value.strip()

        # Ưu tiên tìm trong các object dữ liệu thường gặp
        for key in ("data", "Data", "result", "Result"):
            if key in value:
                token = find_access_token(value[key])

                if token:
                    return token

        # Tìm tiếp trong các object hoặc list lồng nhau
        for child_value in value.values():
            if isinstance(child_value, (dict, list)):
                token = find_access_token(child_value)

                if token:
                    return token

    elif isinstance(value, list):
        for item in value:
            token = find_access_token(item)

            if token:
                return token

    elif isinstance(value, str):
        text_value = value.strip()

        # Trường hợp AMIS trả data là một chuỗi JSON
        if text_value.startswith(("{", "[")):
            try:
                return find_access_token(json.loads(text_value))
            except json.JSONDecodeError:
                return None

        # Trường hợp data chính là chuỗi token
        if len(text_value) >= 40 and " " not in text_value:
            return text_value

    return None
def get_access_token() -> str:
    """Lấy access token từ AMIS CRM."""

    response = requests.post(
        f"{API_BASE}/Account",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=30,
    )

    print("HTTP lay token:", response.status_code)

    payload = parse_json_response(response)

    success = payload.get(
        "success",
        payload.get("Success"),
    )

    if not response.ok or success is False:
        print(
            "AMIS user_msg:",
            payload.get("user_msg")
            or payload.get("UserMsg")
            or payload.get("message"),
        )

        print(
            "AMIS dev_msg:",
            payload.get("dev_msg")
            or payload.get("DevMsg"),
        )

        stop("AMIS tu choi cap token. Kiem tra AppID va ma bao mat.")

    access_token = find_access_token(payload)

    if not access_token:
        print(
            "Cac truong phan hoi:",
            list(payload.keys()),
        )

        data = payload.get("data")
        if data is None:
            data = payload.get("Data")

        if isinstance(data, dict):
            print(
                "Cac truong trong data:",
                list(data.keys()),
            )
        else:
            print(
                "Kieu du lieu data:",
                type(data).__name__,
            )

        print(
            "Thong bao AMIS:",
            payload.get("user_msg")
            or payload.get("UserMsg")
            or payload.get("dev_msg")
            or payload.get("DevMsg")
            or payload.get("message"),
        )

        stop("Khong tim thay access token trong phan hoi AMIS.")

    print("LAY TOKEN THANH CONG")

    return access_token

def get_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Clientid": str(CLIENT_ID),
        "Accept": "application/json",
    }


def get_stocks(
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{API_BASE}/Stocks",
        headers=headers,
        timeout=30,
    )

    print(
        "HTTP lay danh sach kho:",
        response.status_code,
    )

    payload = parse_json_response(response)

    if not response.ok:
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        stop("Khong lay duoc danh sach kho.")

    stocks = extract_list(decode_data(payload))

    if not stocks:
        stop("AMIS khong tra ve danh sach kho.")

    return stocks


def select_stock(
    stocks: list[dict[str, Any]],
) -> dict[str, Any]:
    for stock in stocks:
        stock_code = str(
            stock.get("stock_code")
            or stock.get("StockCode")
            or stock.get("code")
            or ""
        ).strip()

        stock_name = str(
            stock.get("stock_name")
            or stock.get("StockName")
            or stock.get("name")
            or ""
        ).strip()

        if (
            stock_code.casefold() == STOCK_CODE.casefold()
            or STOCK_CODE.casefold() in stock_name.casefold()
        ):
            return stock

    stop(
        f"Khong tim thay kho '{STOCK_CODE}'. "
        "Kiem tra AMIS_STOCK_CODE trong .env."
    )


def get_stock_id(
    selected_stock: dict[str, Any],
) -> str:
    stock_id = (
        selected_stock.get("async_id")
        or selected_stock.get("AsyncId")
        or selected_stock.get("stock_id")
        or selected_stock.get("StockId")
        or selected_stock.get("id")
        or selected_stock.get("Id")
    )

    if not stock_id:
        stop("Tim thay kho nhung khong tim thay ID kho.")

    return str(stock_id)


def get_inventory(
    headers: dict[str, str],
    stock_id: str,
) -> list[dict[str, Any]]:
    all_inventory: list[dict[str, Any]] = []

    page = 1
    page_size = 50

    while True:
        response = requests.get(
            f"{API_BASE}/Stocks/product_ledger",
            headers=headers,
            params={
                "page": page,
                "pageSize": page_size,
                "stockID": stock_id,
            },
            timeout=60,
        )

        print(
            f"Trang {page}: HTTP "
            f"{response.status_code}"
        )

        payload = parse_json_response(response)

        if not response.ok:
            print(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                )
            )
            stop(
                f"Khong lay duoc ton kho trang {page}."
            )

        page_items = extract_list(
            decode_data(payload)
        )

        if not page_items:
            break

        all_inventory.extend(page_items)

        total_pages = (
            payload.get("total_pages")
            or payload.get("TotalPages")
            or payload.get("totalPages")
        )

        if total_pages is not None:
            try:
                if page >= int(total_pages):
                    break
            except (TypeError, ValueError):
                pass

        if len(page_items) < page_size:
            break

        page += 1

        if page > 100:
            stop("Vuot qua 100 trang. Da dung dong bo.")

    return all_inventory


def get_batch_inventory() -> list[dict[str, Any]]:
    """Lay toan bo ton kho theo lo tu API dang duoc giao dien AMIS su dung."""
    headers = {
        "Authorization": f"Bearer {AMIS_APP_TOKEN}",
        "companycode": AMIS_COMPANY_CODE,
        "X-MISA-Language": "vi-VN",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    all_rows: list[dict[str, Any]] = []
    page = 1
    page_size = 100

    while True:
        filters = [
            {
                "Operator": 0, "Value": False, "Property": "IsSetProduct",
                "InputType": 17, "Group": "", "Addition": 1,
                "IsFromFormula": False, "FromFilterCustom": True,
            },
            {
                "Operator": 0, "Value": False, "Property": "InActive",
                "InputType": 17, "Group": "", "Addition": 1,
                "IsFromFormula": False, "FromFilterCustom": True,
            },
            {
                "Operator": 11, "Value": int(AMIS_BATCH_STOCK_ID),
                "Property": "StockID", "InputType": 1, "Group": "",
                "Addition": 1, "IsFromFormula": False,
                "FromFilterCustom": True,
            },
            {
                "Operator": 2, "Value": 0,
                "Property": "StockQuantitySummary", "InputType": 12,
                "Group": "", "Addition": 1, "IsFromFormula": False,
                "FromFilterCustom": True,
            },
            {
                "Operator": 0, "Value": False,
                "Property": "IsCheckShowOrderDetail", "InputType": 17,
                "Group": "", "Addition": 1, "IsFromFormula": False,
                "FromFilterCustom": True,
            },
        ]
        payload = {
            "Columns": BATCH_COLUMNS,
            "Sorts": [{"SortBy": "ExpiryDate", "SortDirection": 0}],
            "Start": (page - 1) * page_size,
            "Page": page,
            "PageSize": page_size,
            "Filters": filters,
            "Formula": "",
            "LayoutCode": "Product",
            "DefaultTotal": False,
            "IsMappingData": False,
            "IsApproved": False,
            "CustomPagingData": {
                "IsGetStockIfNotHaveProductCode": True,
                "IsSetProduct": False,
                "QuantityFromOrderStatus": "5",
                "IncludeDistributorOrder": False,
                "DeductMinimumStock": False,
                "numberUnit": 0,
            },
            "IsUsedELTS": True,
            "ListGmailPage": [],
            "ListFacebookPage": {},
            "IsGetCache": True,
            "IsCheckInactive": False,
            "IsConverted": False,
            "SessionID": str(uuid.uuid4()),
            "LayoutCodeCheckPermission": "Product",
            "AISearchKeyword": "",
            "SkipNormalSearch": False,
        }
        response = requests.post(
            f"{AMIS_APP_API_BASE}/Stock/productLedgerBatch/Paging",
            params={"saveWarehouse": "true"},
            headers=headers,
            json=payload,
            timeout=120,
        )
        print(f"Trang lo {page}: HTTP {response.status_code}")
        result = parse_json_response(response)

        if not response.ok or result.get("Success") is False:
            stop(
                "Khong lay duoc ton kho theo lo. "
                "AMIS_APP_TOKEN co the da het han."
            )

        rows = extract_list(decode_data(result))
        all_rows.extend(rows)
        total = to_integer(result.get("Total"))

        if not rows or (total and len(all_rows) >= total):
            break

        page += 1

        if page > 200:
            stop("Vuot qua 200 trang ton kho theo lo.")

    return all_rows


def build_batch_map(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, int, str], dict[str, Any]]:
    """Gop ton theo khoa (ma hang, kho, so lo)."""
    batch_map: dict[tuple[str, int, str], dict[str, Any]] = {}

    for row in rows:
        product_code = first_text(row, "ProductCode", "product_code")
        normalized_code = normalize_code(product_code)
        batch_number = first_text(row, "BatchNumber", "batch_number")
        stock_id = to_integer(row.get("StockID") or row.get("stock_id"))

        if not normalized_code or not batch_number or not stock_id:
            continue

        key = (normalized_code, stock_id, batch_number.casefold())
        quantity = to_integer(
            row.get("StockQuantitySummary")
            or row.get("stock_quantity_summary")
        )
        existing = batch_map.get(key)

        if existing:
            existing["quantity"] += quantity
            continue

        batch_map[key] = {
            "product_code": product_code,
            "product_async_id": first_text(row, "AsyncID", "async_id"),
            "stock_id": stock_id,
            "batch_number": batch_number,
            "expiry_date": parse_datetime(
                row.get("ExpiryDate") or row.get("expiry_date")
            ),
            "quantity": quantity,
        }

    return batch_map


def build_inventory_map(
    inventory: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    inventory_map: dict[str, dict[str, Any]] = {}

    for item in inventory:
        original_code = first_text(
            item,
            "product_code",
            "ProductCode",
            "inventory_item_code",
            "InventoryItemCode",
            "code",
        )

        normalized_code = normalize_code(original_code)

        if not normalized_code:
            continue

        stock = to_integer(
            item.get("main_stock_quantity")
        )

        reserved = to_integer(
            item.get("amount_summary")
        )

        available = to_integer(
            item.get("order_quantity")
        )

        product_name = first_text(
            item,
            "product_name",
            "ProductName",
            "inventory_item_name",
            "InventoryItemName",
            "name",
        )

        # Cac dong an chi/ky hieu thu tien trong CRM khong phai hang ton kho.
        if "phiếu thu ký hiệu" in product_name.casefold():
            inventory_map.pop(normalized_code, None)
            continue

        explicit_model = first_text(
            item,
            "model",
            "model_name",
            "ModelName",
        )
        explicit_color = first_text(
            item,
            "color",
            "colour",
            "color_name",
            "ColorName",
        )
        parsed_model, parsed_color = split_model_color(
            product_name or original_code
        )

        inventory_map[normalized_code] = {
            "code": original_code,
            # Cot model trong he thong la bat buoc. Neu AMIS khong tra ten
            # san pham, tach model/mau truc tiep tu ma hang lam du lieu du phong.
            "model": explicit_model or parsed_model or original_code,
            "color": explicit_color or parsed_color,
            "category": first_text(
                item,
                "category_name",
                "CategoryName",
                "product_category_name",
                "ProductCategoryName",
                "group_name",
                "GroupName",
            ),
            "unit": first_text(
                item,
                "unit_name",
                "UnitName",
                "main_unit_name",
                "MainUnitName",
                "unit",
            ) or "Chiếc",
            "stock": stock,
            "reserved": reserved,
            "available": available,
        }

    return inventory_map


def update_supabase(
    inventory_map: dict[str, dict[str, Any]],
) -> None:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    updated_count = 0
    inserted_count = 0
    unchanged_count = 0
    missing_in_amis: list[str] = []

    with engine.begin() as connection:
        products = connection.execute(
            text(
                """
                SELECT id, code, stock, reserved
                FROM products
                ORDER BY id
                """
            )
        ).mappings().all()

        existing_by_code = {
            normalize_code(product["code"]): product
            for product in products
            if normalize_code(product["code"])
        }

        for normalized_code, product in existing_by_code.items():
            product_code = str(
                product["code"] or ""
            ).strip()

            amis_item = inventory_map.get(normalized_code)

            if not amis_item:
                missing_in_amis.append(product_code)
                continue

            new_stock = amis_item["stock"]
            new_reserved = amis_item["reserved"]

            old_stock = to_integer(product["stock"])
            old_reserved = to_integer(product["reserved"])

            if (
                old_stock == new_stock
                and old_reserved == new_reserved
            ):
                unchanged_count += 1
                continue

            connection.execute(
                text(
                    """
                    UPDATE products
                    SET
                        stock = :stock,
                        reserved = :reserved,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :product_id
                    """
                ),
                {
                    "stock": new_stock,
                    "reserved": new_reserved,
                    "product_id": product["id"],
                },
            )

            updated_count += 1

        # Vong lap cu chi duyet cac ma da co trong database nen ma moi tren
        # AMIS bi bo qua. Duyet nguoc lai inventory_map de them cac ma con thieu.
        for normalized_code, amis_item in inventory_map.items():
            if normalized_code in existing_by_code:
                continue

            connection.execute(
                text(
                    """
                    INSERT INTO products (
                        code,
                        model,
                        color,
                        category,
                        unit,
                        stock,
                        reserved,
                        updated_at
                    )
                    VALUES (
                        :code,
                        :model,
                        :color,
                        :category,
                        :unit,
                        :stock,
                        :reserved,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "code": amis_item["code"],
                    "model": amis_item["model"],
                    "color": amis_item["color"],
                    "category": amis_item["category"],
                    "unit": amis_item["unit"],
                    "stock": amis_item["stock"],
                    "reserved": amis_item["reserved"],
                },
            )

            inserted_count += 1

    engine.dispose()

    print("\n========================================")
    print("DONG BO SUPABASE THANH CONG")
    print("Da cap nhat:", updated_count)
    print("Khong thay doi:", unchanged_count)
    print(
        "Khong tim thay tren AMIS:",
        len(missing_in_amis),
    )
    print("========================================")

    if inserted_count:
        print(
            f"\nGHI CHÚ: Đã thêm mới {inserted_count} "
            "mã hàng từ AMIS."
        )

    if missing_in_amis:
        print("\n20 MA KHONG TIM THAY TREN AMIS:")

        for code in missing_in_amis[:20]:
            print("-", code)


def update_product_lots(
    batch_map: dict[tuple[str, int, str], dict[str, Any]],
    stock_id: int,
) -> None:
    """Thay toan bo snapshot lo cua mot kho trong mot transaction."""
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    inserted_count = 0
    missing_products: list[str] = []

    with engine.begin() as connection:
        products = connection.execute(
            text("SELECT id, code FROM products ORDER BY id")
        ).mappings().all()
        products_by_code = {
            normalize_code(product["code"]): product
            for product in products
            if normalize_code(product["code"])
        }

        # API tra ve snapshot day du cua kho. Xoa snapshot cu trong cung
        # transaction de cac lo da het ton khong bi giu lai.
        connection.execute(
            text("DELETE FROM product_lots WHERE stock_id = :stock_id"),
            {"stock_id": stock_id},
        )

        for (normalized_code, _, _), batch in batch_map.items():
            product = products_by_code.get(normalized_code)

            if not product:
                missing_products.append(batch["product_code"])
                continue

            if batch["product_async_id"]:
                connection.execute(
                    text(
                        """
                        UPDATE products
                        SET amis_async_id = :amis_async_id
                        WHERE id = :product_id
                        """
                    ),
                    {
                        "amis_async_id": batch["product_async_id"],
                        "product_id": product["id"],
                    },
                )

            connection.execute(
                text(
                    """
                    INSERT INTO product_lots (
                        product_id,
                        stock_id,
                        batch_number,
                        expiry_date,
                        quantity,
                        amis_product_async_id,
                        updated_at
                    )
                    VALUES (
                        :product_id,
                        :stock_id,
                        :batch_number,
                        :expiry_date,
                        :quantity,
                        :amis_product_async_id,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "product_id": product["id"],
                    "stock_id": batch["stock_id"],
                    "batch_number": batch["batch_number"],
                    "expiry_date": batch["expiry_date"],
                    "quantity": batch["quantity"],
                    "amis_product_async_id": batch["product_async_id"] or None,
                },
            )
            inserted_count += 1

    engine.dispose()

    print("\n========================================")
    print("DONG BO TON KHO THEO LO THANH CONG")
    print("So lo da luu:", inserted_count)
    print("Ma hang chua co trong products:", len(missing_products))
    print("========================================")

    for code in missing_products[:20]:
        print("-", code)


def sync_batch_inventory() -> None:
    missing = []

    if not AMIS_APP_TOKEN:
        missing.append("AMIS_APP_TOKEN")
    if not AMIS_COMPANY_CODE:
        missing.append("AMIS_COMPANY_CODE")
    if not AMIS_BATCH_STOCK_ID:
        missing.append("AMIS_BATCH_STOCK_ID")

    if missing:
        stop("Thieu cau hinh: " + ", ".join(missing))

    try:
        numeric_stock_id = int(AMIS_BATCH_STOCK_ID)
    except ValueError:
        stop("AMIS_BATCH_STOCK_ID phai la so nguyen, vi du 19.")

    rows = get_batch_inventory()
    batch_map = build_batch_map(rows)
    print("Tong dong API theo lo:", len(rows))
    print("Tong lo hop le:", len(batch_map))
    update_product_lots(batch_map, numeric_stock_id)


def main() -> None:
    if not DATABASE_URL:
        stop("Thieu DATABASE_URL trong .env")

    if AMIS_BATCH_ONLY:
        sync_batch_inventory()
        return

    if not CLIENT_ID:
        stop("Thieu AMIS_CLIENT_ID trong .env")

    if not CLIENT_SECRET:
        stop("Thieu AMIS_CLIENT_SECRET trong .env")

    access_token = get_access_token()
    headers = get_headers(access_token)

    stocks = get_stocks(headers)
    selected_stock = select_stock(stocks)
    stock_id = get_stock_id(selected_stock)

    print("\nDA CHON KHO:")
    print(
        selected_stock.get("stock_code"),
        "-",
        selected_stock.get("stock_name"),
    )

    inventory = get_inventory(
        headers,
        stock_id,
    )

    print(
        "\nTong so dong ton kho AMIS:",
        len(inventory),
    )

    inventory_map = build_inventory_map(inventory)

    print(
        "Tong so ma hang AMIS:",
        len(inventory_map),
    )

    update_supabase(inventory_map)

    batch_settings = (
        AMIS_APP_TOKEN,
        AMIS_COMPANY_CODE,
        AMIS_BATCH_STOCK_ID,
    )
    if all(batch_settings):
        sync_batch_inventory()
    elif any(batch_settings):
        stop(
            "Cau hinh dong bo lo chua du. Can AMIS_APP_TOKEN, "
            "AMIS_COMPANY_CODE va AMIS_BATCH_STOCK_ID."
        )
    else:
        print(
            "\nBo qua dong bo theo lo vi chua cau hinh "
            "AMIS_APP_TOKEN."
        )


if __name__ == "__main__":
    main()
