"""AMIS browser-session refresh, based on the authentication flow in its web app."""
import argparse
import json
import os
import tempfile
from pathlib import Path

import requests


REFRESH_URL = "https://amisapp.misa.vn/crm/g1/api/auth/auth/refreshtoken"
STATE_PATH = Path(__file__).with_name(".env.amis-session.json")


def valid(value):
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"undefined", "null", "none"}


class AmisAppSession:
    def __init__(self, token="", company_code="", refresh_token="", state_path=STATE_PATH):
        self.state_path = Path(state_path)
        self.http = requests.Session()
        self.state = {"token": token, "companycode": company_code, "refresh_token": refresh_token}
        if self.state_path.exists():
            saved = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
            if company_code and saved.get("companycode") != company_code:
                raise ValueError("File phien AMIS thuoc cong ty khac voi cau hinh.")
            self.state.update(saved)
        self.state = {key: value for key, value in self.state.items() if valid(value)}

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp = tempfile.mkstemp(prefix=".env.amis-session-", dir=self.state_path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.state, stream)
            os.replace(temp, self.state_path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def import_state(self, value):
        state = {}
        for key in ("token", "refresh_token", "companycode", ".ASPXAUTH"):
            item = value.get(key) or value.get("AMIS.CRM_" + key)
            if valid(item):
                state[key] = item
        if not all(valid(state.get(key))
                   for key in ("token", "refresh_token", "companycode")):
            raise ValueError("Can token, refresh_token va companycode trong file phien.")
        self.state = state
        self.save()

    def refresh(self):
        if not self.state.get("refresh_token"):
            raise ValueError("Thieu refresh_token AMIS. Can nhap phien tu trinh duyet mot lan.")
        headers = {"Accept": "application/json", "companycode": self.state.get("companycode", ""),
                   "Authorization": "Bearer " + self.state.get("token", ""), "X-MISA-Language": "vi-VN"}
        if self.state.get(".ASPXAUTH"):
            headers["crm2-aspxauth"] = self.state[".ASPXAUTH"]
        response = self.http.post(REFRESH_URL, json={
            "access_token": self.state.get("token"),
            "refresh_token": self.state["refresh_token"],
        }, headers=headers,
            timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"AMIS khong gia han duoc phien (HTTP {response.status_code}). Can dang nhap lai.")
        result = response.json()
        data = result.get("Data")
        if result.get("Success") is not True or not isinstance(data, dict) or not data.get("token"):
            raise ValueError("AMIS tu choi gia han. Phien co the het han hoac da bi thu hoi; can dang nhap lai.")
        # Refresh tokens can rotate. Persist the returned pair before another API call.
        for key in ("token", "refresh_token", ".ASPXAUTH"):
            if valid(data.get(key)):
                self.state[key] = data[key]
        self.save()

    def request(self, method, url, **kwargs):
        if not url.startswith("https://amisapp.misa.vn/crm/g1/api/business/"):
            raise ValueError("Chi cho phep API business AMIS da xac dinh.")
        extra_headers = kwargs.pop("headers", {})
        kwargs.setdefault("timeout", 60)
        kwargs["allow_redirects"] = False
        for attempt in range(2):
            headers = dict(extra_headers)
            headers.update({"Authorization": "Bearer " + self.state.get("token", ""),
                            "companycode": self.state.get("companycode", ""),
                            "X-MISA-Language": "vi-VN"})
            if self.state.get(".ASPXAUTH"):
                headers["crm2-aspxauth"] = self.state[".ASPXAUTH"]
            response = self.http.request(method, url, headers=headers, **kwargs)
            if response.status_code != 401:
                return response
            if attempt == 0:
                self.refresh()
        raise ValueError("API van tu choi sau khi gia han; khong ghi de du lieu ton kho.")


def main():
    parser = argparse.ArgumentParser(description="Nhap va kiem tra phien AMIS, khong in token.")
    parser.add_argument("--import-session", type=Path)
    parser.add_argument("--refresh", action="store_true", help="Thu gia han that va luu token moi.")
    args = parser.parse_args()
    session = AmisAppSession()
    try:
        if args.import_session:
            session.import_state(json.loads(args.import_session.read_text(encoding="utf-8-sig")))
        if args.refresh:
            session.refresh()
            print("Gia han token thanh cong; da luu phien moi.")
        response = session.request("GET", "https://amisapp.misa.vn/crm/g1/api/business/Stock/productLedger/latest-warehouse")
        response.raise_for_status()
        if response.json().get("Success") is not True:
            raise ValueError("Phien chua truy cap duoc kho.")
        print("Kiem tra API kho thanh cong. Khong ghi database.")
    except (OSError, ValueError, requests.RequestException) as error:
        print("LOI: " + (str(error) if isinstance(error, ValueError) else type(error).__name__))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
