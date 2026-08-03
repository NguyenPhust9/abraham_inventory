import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(override=True)
API_BASE = os.getenv(
    "AMIS_API_BASE",
    "https://crmconnect.misa.vn/api/v2",
).rstrip("/")

CLIENT_ID = os.getenv("AMIS_CLIENT_ID")
CLIENT_SECRET = os.getenv("AMIS_CLIENT_SECRET")


def find_access_token(value):
    if isinstance(value, dict):
        for key, child_value in value.items():
            normalized_key = (
                str(key).strip().lower().replace("_", "").replace("-", "")
            )
            if normalized_key in {
                "accesstoken",
                "token",
                "bearertoken",
                "authorizationtoken",
            }:
                if isinstance(child_value, str) and child_value.strip():
                    return child_value.strip()

        for key in ("data", "Data", "result", "Result"):
            if key in value:
                token = find_access_token(value[key])
                if token:
                    return token

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
        if text_value.startswith(("{", "[")):
            try:
                return find_access_token(json.loads(text_value))
            except json.JSONDecodeError:
                return None
        if len(text_value) >= 40 and " " not in text_value:
            return text_value

    return None


def get_access_token():
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
    payload = response.json()
    token = find_access_token(payload)

    if not token:
        print("Khong tim thay token, in ra payload de kiem tra:")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])
        sys.exit(1)

    return token


def main():
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Clientid": str(CLIENT_ID),
        "Accept": "application/json",
    }

    response = requests.get(
        f"{API_BASE}/Stocks/product_ledger",
        headers=headers,
        params={"page": 1, "pageSize": 1, "stockID": ""},
        timeout=30,
    )

    print("HTTP status:", response.status_code)

    payload = response.json()
    print("\n===== TOAN BO RESPONSE (1 SAN PHAM MAU) =====")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()