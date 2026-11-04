"""Read Routing/Grid using a locally saved browser cURL request."""
import argparse
import copy
import json
import re
from pathlib import Path

import requests


def read_request(path):
    source = path.read_text(encoding="utf-8-sig")
    url = re.search(r"--url\s+'([^']+)'", source)
    body = re.search(r"--data-raw\s+'(.*?)'\s*$", source, re.S)
    if not url or not body:
        raise ValueError("Can cURL co --url va --data-raw JSON.")
    if url.group(1) != "https://amisapp.misa.vn/crm/g1/api/business/Routing/Grid":
        raise ValueError("Chi chap nhan endpoint AMIS Routing/Grid.")
    headers = {}
    for name, value in re.findall(r"-H\s+'([^:']+):\s*([^']*)'", source):
        if name.lower() in {"authorization", "companycode", "layoutcode", "x-misa-language", "accept", "content-type", "referer", "origin"}:
            headers[name] = value
    if not any(k.lower() == "authorization" for k in headers):
        raise ValueError("Thieu Authorization trong request.")
    return url.group(1), headers, json.loads(body.group(1))


def unpack(value):
    if isinstance(value, str):
        try:
            return unpack(json.loads(value))
        except (ValueError, TypeError):
            return None
    if isinstance(value, list):
        if all(isinstance(row, dict) for row in value):
            return value
        return None
    if isinstance(value, dict):
        for key in ("Data", "data", "Items", "items", "Rows", "rows", "Result", "result", "List", "list"):
            if key in value:
                rows = unpack(value[key])
                if rows is not None:
                    return rows
    return None


def fetch(url, headers, template):
    rows = []
    seen_pages = set()
    size = int(template.get("PageSize", 20))
    if size < 1:
        raise ValueError("PageSize phai lon hon 0.")
    with requests.Session() as session:
        for page in range(1, 1001):
            payload = copy.deepcopy(template)
            payload.update(Page=page, Start=(page - 1) * size)
            response = session.post(url, headers=headers, json=payload, timeout=60, allow_redirects=False)
            print(f"Trang {page}: HTTP {response.status_code}")
            if response.status_code in (301, 302, 401, 403):
                raise ValueError("Phien dang nhap het han hoac khong du quyen. Luu lai cURL moi.")
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and (result.get("Success") is False or result.get("success") is False):
                raise ValueError("AMIS tu choi request. Kiem tra phien dang nhap va quyen Tuy en ban hang.")
            batch = unpack(result)
            if batch is None:
                raise ValueError("Chua nhan dien duoc cau truc danh sach trong Response.")
            if batch and not all("RoutingName" in row or "RoutingCode" in row for row in batch):
                raise ValueError("Response khong chua cac truong tuyen RoutingName/RoutingCode.")
            fingerprint = json.dumps(batch, sort_keys=True, ensure_ascii=False)
            if batch and fingerprint in seen_pages:
                raise ValueError("API lap lai trang; dung de tranh xuat du lieu thieu hoac trung.")
            seen_pages.add(fingerprint)
            rows.extend(batch)
            if len(batch) < size:
                return rows
    raise ValueError("Vuot gioi han 1000 trang.")


def main():
    parser = argparse.ArgumentParser(description="Lay danh sach tuyen AMIS, xuat JSON, khong ghi database.")
    parser.add_argument("--request", type=Path, default=Path(__file__).with_name("amis_routing_request.txt"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data" / "amis_routing.json")
    args = parser.parse_args()
    try:
        url, headers, payload = read_request(args.request)
        rows = fetch(url, headers, payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Thanh cong: {len(rows)} tuyen. File: {args.output}")
    except (OSError, ValueError, requests.RequestException) as error:
        print(f"LOI: {type(error).__name__}. " + (str(error) if isinstance(error, ValueError) else "Kiem tra file request, ket noi mang va phien dang nhap."))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
