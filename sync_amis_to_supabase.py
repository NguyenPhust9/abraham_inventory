import json
import os
import sys
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


def to_integer(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0

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


def build_inventory_map(
    inventory: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    inventory_map: dict[str, dict[str, Any]] = {}

    for item in inventory:
        original_code = str(
            item.get("product_code") or ""
        ).strip()

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

        inventory_map[normalized_code] = {
            "code": original_code,
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

        for product in products:
            product_code = str(
                product["code"] or ""
            ).strip()

            normalized_code = normalize_code(product_code)

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
                        updated_at = NOW()
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

    print("\n========================================")
    print("DONG BO SUPABASE THANH CONG")
    print("Da cap nhat:", updated_count)
    print("Khong thay doi:", unchanged_count)
    print(
        "Khong tim thay tren AMIS:",
        len(missing_in_amis),
    )
    print("========================================")

    if missing_in_amis:
        print("\n20 MA KHONG TIM THAY TREN AMIS:")

        for code in missing_in_amis[:20]:
            print("-", code)


def main() -> None:
    if not CLIENT_ID:
        stop("Thieu AMIS_CLIENT_ID trong .env")

    if not CLIENT_SECRET:
        stop("Thieu AMIS_CLIENT_SECRET trong .env")

    if not DATABASE_URL:
        stop("Thieu DATABASE_URL trong .env")

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


if __name__ == "__main__":
    main()