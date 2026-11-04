"""Export employee routing journals and visit photos using observed AMIS requests."""
import argparse
import copy
import json
import re
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path

import requests

from fetch_amis_routing import read_request

BASE = "https://amisapp.misa.vn/crm/g1/api/business"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class Client:
    def __init__(self, headers):
        self.session = requests.Session()
        self.session.headers.update(headers)

    def get(self, path, payload=None):
        response = self.session.request("POST" if payload is not None else "GET", BASE + path,
                                        json=payload, timeout=60, allow_redirects=False)
        if response.status_code in (301, 302, 401, 403):
            raise ValueError("Phien AMIS het han hoac khong du quyen; cap nhat file cURL.")
        response.raise_for_status()
        result = response.json()
        if result.get("Success") is not True:
            raise ValueError(f"AMIS tu choi request {path.split('?')[0]}")
        return result

    def pages(self, path, template):
        rows, seen, seen_rows = [], set(), set()
        activity_count = 0
        size = int(template.get("PageSize", 10))
        for page in range(1, 1001):
            payload = copy.deepcopy(template)
            payload.update(Start=(page - 1) * size)
            if "Page" in payload:
                payload["Page"] = page
            result = self.get(path, payload)
            batch = result.get("Data")
            if not isinstance(batch, list):
                raise ValueError("Khong nhan dien duoc Data dang danh sach.")
            fingerprint = json.dumps(batch, sort_keys=True)
            if batch and fingerprint in seen:
                raise ValueError(f"API lap trang tai {path}.")
            seen.add(fingerprint)
            for row in batch:
                key = json.dumps(row, sort_keys=True)
                if key not in seen_rows:
                    seen_rows.add(key)
                    rows.append(row)
            is_journal = path.startswith("/Routing/RoutingAccount/")
            count = sum(bool(row.get("ActivityID")) for row in batch) if is_journal else len(batch)
            activity_count += count
            # Journals include unpaged automatic GPS points alongside paged activities.
            # Total counts activities, not all returned rows.
            total = result.get("Total")
            if count < size or (isinstance(total, int) and total > 0 and activity_count >= total):
                return rows
        raise ValueError("Vuot gioi han 1000 trang.")


def templates(har_path):
    entries = json.loads(har_path.read_text(encoding="utf-8-sig"))["log"]["entries"]
    employee = account = None
    for entry in entries:
        request = entry["request"]
        url = request["url"]
        if url == BASE + "/Routing/RoutingEmployeePaging":
            employee = json.loads(request["postData"]["text"])
        if re.fullmatch(re.escape(BASE) + r"/Routing/RoutingAccount/\d+", url):
            candidate = json.loads(request["postData"]["text"])
            if candidate["CustomPagingData"].get("FollowStatus") == 1:
                account = candidate
    if employee is None or account is None:
        raise ValueError("HAR thieu RoutingEmployeePaging hoac RoutingAccount (Da ghe tham).")
    return employee, account


def run(args):
    _, headers, _ = read_request(args.request)
    employee_template, account_template = templates(args.har)
    client = Client(headers)
    company = next(v for k, v in headers.items() if k.lower() == "companycode")
    employees = client.pages("/Routing/RoutingEmployeePaging", employee_template)
    if args.employee:
        employees = [e for e in employees if e["ID"] in args.employee]
        if set(args.employee) != {e["ID"] for e in employees}:
            raise ValueError("Nhan vien yeu cau khong nam trong danh sach duoc cap quyen.")
    print(f"Nhan vien: {len(employees)}", flush=True)
    total_events = total_photos = 0
    day = args.start_date
    while day <= args.end_date:
        folder = args.output / day.isoformat()
        summary = []
        for employee in employees:
            employee_id = employee["ID"]
            payload = copy.deepcopy(account_template)
            # Use noon in Vietnam so the requested local calendar date is unambiguous.
            selected = datetime.combine(day, time(12), tzinfo=timezone(timedelta(hours=7)))
            payload["CustomPagingData"]["SelectedDate"] = selected.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            events = client.pages(f"/Routing/RoutingAccount/{employee_id}", payload)
            locations = client.get(f"/Routing/CheckInLocation/{employee_id}/{day.strftime('%m-%d-%Y')}")["Data"]
            employee_folder = folder / str(employee_id)
            # Save the journal before downloading photos so metadata survives an interrupted run.
            record = {"employee": {k: employee.get(k) for k in ("ID", "EmployeeID", "EmployeeCode", "FullName", "OrganizationUnitName")},
                      "date": day.isoformat(), "events": events, "locations": locations, "photos": {}}
            save(employee_folder / "journal.json", record)
            location_rows = locations if isinstance(locations, list) else []
            activities = sorted({int(e["ActivityID"]) for e in events + location_rows if e.get("ActivityID")})
            photo_count = 0
            for activity in activities:
                images = client.get(f"/Attachment/GetRoutingImage/{activity}")["Data"]
                if not isinstance(images, list):
                    raise ValueError("Danh sach anh khong hop le.")
                record["photos"][str(activity)] = images
                for image in images:
                    image_id = str(image["ID"])
                    ext = image.get("FileExtention", "")
                    if not re.fullmatch(r"[a-zA-Z0-9-]+", image_id) or not re.fullmatch(r"\.(?i:jpg|jpeg|png|webp|gif|heic)", ext):
                        raise ValueError("Ma anh hoac dinh dang anh khong hop le.")
                    destination = employee_folder / str(activity) / (image_id + ext)
                    if not destination.exists():
                        response = client.session.get(BASE + "/images", params={"companycode": company, "id": image_id + ext,
                            "type": 3, "isTemp": "false", "mode": "pad"}, timeout=60, allow_redirects=False)
                        response.raise_for_status()
                        if not response.headers.get("Content-Type", "").startswith("image/"):
                            raise ValueError("API anh khong tra ve tap tin anh.")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(response.content)
                    image["local_path"] = str(destination.relative_to(args.output))
                    photo_count += 1
                save(employee_folder / "journal.json", record)
            total_events += len(events)
            total_photos += photo_count
            summary.append({"employee_id": employee_id, "name": employee.get("FullName"), "events": len(events),
                            "activities": len(activities), "photos": photo_count})
            save(folder / "summary.json", summary)
            print(f"{day} | NV {employee_id}: {len(events)} su kien, {len(activities)} hoat dong, {photo_count} anh", flush=True)
        day += timedelta(days=1)
    print(f"HOAN TAT: {total_events} su kien, {total_photos} anh. Thu muc: {args.output}")


def main():
    root = Path(__file__).parent
    parser = argparse.ArgumentParser(description="Tai nhat ky di tuyen va anh, khong can bam tung nhan vien.")
    parser.add_argument("--har", required=True, type=Path, help="HAR mau chua request nhan vien va Da ghe tham.")
    parser.add_argument("--request", type=Path, default=root / "amis_routing_request.txt")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--employee", type=int, action="append", help="Loc ID nhan vien; mac dinh lay tat ca trong pham vi quyen.")
    parser.add_argument("--output", type=Path, default=root / "data" / "amis_visits")
    args = parser.parse_args()
    args.end_date = args.end_date or args.start_date
    if args.end_date < args.start_date:
        parser.error("end-date phai tu start-date tro di")
    try:
        run(args)
    except (OSError, ValueError, requests.RequestException) as error:
        print("LOI: " + (str(error) if isinstance(error, ValueError) else type(error).__name__))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
