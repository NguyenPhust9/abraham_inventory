import json
import os
import sys
from collections import Counter
from typing import Any

import requests
from dotenv import load_dotenv


# Đọc các biến cấu hình trong file .env
load_dotenv()

API_BASE = os.getenv(
    "AMIS_API_BASE",
    "https://crmconnect.misa.vn/api/v2",
).rstrip("/")

CLIENT_ID = os.getenv("AMIS_CLIENT_ID")
CLIENT_SECRET = os.getenv("AMIS_CLIENT_SECRET")

# Mã kho cần lấy tồn
STOCK_CODE = os.getenv(
    "AMIS_STOCK_CODE",
    "HCM 3",
).strip()

# Mã sản phẩm dùng để đối chiếu với giao diện AMIS
TEST_PRODUCT_CODE = os.getenv(
    "AMIS_TEST_PRODUCT_CODE",
    "3DAO20 - Cam",
).strip()


def stop(message: str) -> None:
    """In lỗi và dừng chương trình."""
    print(f"\nLOI: {message}")
    sys.exit(1)


def parse_json_response(
    response: requests.Response,
) -> dict[str, Any]:
    """Chuyển phản hồi API thành dictionary."""
    try:
        payload = response.json()
    except ValueError:
        stop(
            f"API khong tra JSON. HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    if not isinstance(payload, dict):
        stop("Du lieu API tra ve khong dung dinh dang object.")

    return payload


def decode_data(payload: dict[str, Any]) -> Any:
    """Lấy phần data từ phản hồi API."""
    data = payload.get("data")

    if data is None:
        data = payload.get("Data")

    # Một số API MISA trả data dưới dạng chuỗi JSON
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    return data


def extract_list(data: Any) -> list[dict[str, Any]]:
    """Tìm danh sách bản ghi trong data API."""
    if isinstance(data, list):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    if isinstance(data, dict):
        possible_keys = (
            "data",
            "Data",
            "items",
            "Items",
            "records",
            "Records",
            "result",
            "Result",
        )

        for key in possible_keys:
            value = data.get(key)

            if isinstance(value, list):
                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

    return []


def to_number(value: Any) -> float:
    """Chuyển dữ liệu API thành số."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def get_access_token() -> str:
    """Lấy access token từ AMIS CRM."""
    token_response = requests.post(
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

    print(
        "HTTP lay token:",
        token_response.status_code,
    )

    token_payload = parse_json_response(token_response)

    if not token_response.ok:
        print(
            json.dumps(
                token_payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        stop("Khong lay duoc token AMIS.")

    token_data = decode_data(token_payload)

    if isinstance(token_data, dict):
        access_token = (
            token_data.get("access_token")
            or token_data.get("AccessToken")
            or token_data.get("token")
            or token_data.get("Token")
        )
    else:
        access_token = token_data

    if not access_token:
        print(
            json.dumps(
                token_payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        stop("Khong tim thay access token.")

    print("LAY TOKEN THANH CONG")

    return str(access_token)


def get_headers(access_token: str) -> dict[str, str]:
    """Tạo header dùng cho các API AMIS."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Clientid": str(CLIENT_ID),
        "Accept": "application/json",
    }


def get_stocks(
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    """Lấy danh sách kho từ AMIS."""
    stocks_response = requests.get(
        f"{API_BASE}/Stocks",
        headers=headers,
        timeout=30,
    )

    print(
        "HTTP lay danh sach kho:",
        stocks_response.status_code,
    )

    stocks_payload = parse_json_response(stocks_response)

    if not stocks_response.ok:
        print(
            json.dumps(
                stocks_payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        stop("Khong lay duoc danh sach kho.")

    stocks = extract_list(
        decode_data(stocks_payload)
    )

    if not stocks:
        print(
            json.dumps(
                stocks_payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        stop("API khong tra ve danh sach kho.")

    print(
        f"Tim thay {len(stocks)} kho tren AMIS."
    )

    return stocks


def select_stock(
    stocks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Tìm kho theo mã kho trong file .env."""
    selected_stock = None

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

        print(f"- {stock_code}: {stock_name}")

        if (
            stock_code.casefold()
            == STOCK_CODE.casefold()
            or STOCK_CODE.casefold()
            in stock_name.casefold()
        ):
            selected_stock = stock

    if not selected_stock:
        stop(
            f"Khong tim thay kho '{STOCK_CODE}'. "
            "Kiem tra AMIS_STOCK_CODE trong file .env."
        )

    return selected_stock


def get_stock_id(
    selected_stock: dict[str, Any],
) -> str:
    """Lấy ID kho dùng để gọi API tồn kho."""
    stock_id = (
        selected_stock.get("async_id")
        or selected_stock.get("AsyncId")
        or selected_stock.get("stock_id")
        or selected_stock.get("StockId")
        or selected_stock.get("id")
        or selected_stock.get("Id")
    )

    if not stock_id:
        print(
            json.dumps(
                selected_stock,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        stop("Tim thay kho nhung khong thay ID kho.")

    return str(stock_id)


def get_inventory(
    headers: dict[str, str],
    stock_id: str,
) -> list[dict[str, Any]]:
    """Lấy toàn bộ tồn kho có phân trang."""
    all_inventory: list[dict[str, Any]] = []

    page = 1
    page_size = 50

    while True:
        inventory_response = requests.get(
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
            f"{inventory_response.status_code}"
        )

        inventory_payload = parse_json_response(
            inventory_response
        )

        if not inventory_response.ok:
            print(
                json.dumps(
                    inventory_payload,
                    ensure_ascii=False,
                    indent=2,
                )
            )
            stop(
                f"Khong lay duoc ton kho trang {page}."
            )

        page_items = extract_list(
            decode_data(inventory_payload)
        )

        if not page_items:
            break

        all_inventory.extend(page_items)

        total_pages = (
            inventory_payload.get("total_pages")
            or inventory_payload.get("TotalPages")
            or inventory_payload.get("totalPages")
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

        # Ngăn chương trình lặp vô hạn
        if page > 100:
            stop(
                "Dung chuong trinh vi vuot qua 100 trang."
            )

    return all_inventory


def print_first_inventory(
    all_inventory: list[dict[str, Any]],
) -> None:
    """In thử một dòng dữ liệu tồn kho."""
    if not all_inventory:
        print("Kho khong co du lieu ton.")
        return

    first_item = all_inventory[0]

    print("\nCAC TRUONG API TRA VE:")
    print(", ".join(first_item.keys()))

    print("\nDONG TON KHO DAU TIEN:")
    print(
        json.dumps(
            first_item,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


def check_duplicate_codes(
    all_inventory: list[dict[str, Any]],
) -> None:
    """Kiểm tra API có trả trùng mã hàng không."""
    codes = [
        str(
            item.get("product_code") or ""
        ).strip()
        for item in all_inventory
        if str(
            item.get("product_code") or ""
        ).strip()
    ]

    code_counts = Counter(codes)

    duplicate_codes = {
        code: count
        for code, count in code_counts.items()
        if count > 1
    }

    print("\n===== KIEM TRA TRUNG MA =====")
    print(
        "Tong so dong API:",
        len(all_inventory),
    )
    print(
        "So ma hang duy nhat:",
        len(code_counts),
    )
    print(
        "So ma bi lap:",
        len(duplicate_codes),
    )

    print("\n20 MA BI LAP NHIEU NHAT:")

    sorted_duplicates = sorted(
        duplicate_codes.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for code, count in sorted_duplicates[:20]:
        print(f"{code}: {count} dong")


def check_test_product(
    all_inventory: list[dict[str, Any]],
) -> None:
    """Kiểm tra một mã hàng cụ thể."""
    matches = [
        item
        for item in all_inventory
        if str(
            item.get("product_code") or ""
        ).strip().casefold()
        == TEST_PRODUCT_CODE.casefold()
    ]

    print(
        f"\n===== KIEM TRA MA "
        f"{TEST_PRODUCT_CODE} ====="
    )
    print("So dong tim thay:", len(matches))

    for index, item in enumerate(matches, start=1):
        stock = to_number(
            item.get("main_stock_quantity")
        )

        reserved = to_number(
            item.get("amount_summary")
        )

        available = to_number(
            item.get("order_quantity")
        )

        delivery_quantity = to_number(
            item.get("delivery_quantity")
        )

        print(f"\nDong {index}:")
        print("Ton kho:", stock)
        print("Da dat chua giao:", reserved)
        print("Co the dat:", available)
        print("Delivery quantity:", delivery_quantity)

        print("\nKiem tra:")
        print(
            "Ton - da dat chua giao:",
            stock - reserved,
        )

        print("\nDu lieu goc:")
        print(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

def main() -> None:
    """Chạy chương trình kiểm tra API tồn kho."""
    if not CLIENT_ID:
        stop(
            "Thieu AMIS_CLIENT_ID "
            "trong file .env"
        )

    if not CLIENT_SECRET:
        stop(
            "Thieu AMIS_CLIENT_SECRET "
            "trong file .env"
        )

    access_token = get_access_token()
    headers = get_headers(access_token)

    stocks = get_stocks(headers)
    selected_stock = select_stock(stocks)
    stock_id = get_stock_id(selected_stock)

    print("\nDA CHON KHO:")
    print(
        json.dumps(
            selected_stock,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    all_inventory = get_inventory(
        headers,
        stock_id,
    )

    print("\n========================================")
    print("LAY TON KHO AMIS THANH CONG")
    print("Kho:", STOCK_CODE)
    print(
        "Tong so dong:",
        len(all_inventory),
    )
    print("========================================")

    print_first_inventory(all_inventory)
    check_duplicate_codes(all_inventory)
    check_test_product(all_inventory)


if __name__ == "__main__":
    main()