# -*- coding: utf-8 -*-
import os
import requests
from dotenv import load_dotenv

load_dotenv('.env', override=True)

# ==== SỬA 3 GIÁ TRỊ NÀY ====
TOKEN = "PASTE_TOKEN_THAT_VAO_DAY"          # token JWT lấy được từ bước /Account
APPID = "PASTE_APPID_CLIENTID_THAT"          # AppID/Clientid từ thiết lập AMIS CRM
COMPANY_CODE = "PASTE_COMPANY_CODE_THAT"     # mã công ty/tenant
# ============================

base = os.getenv("AMIS_API_BASE").rstrip("/")
url = f"{base}/Stocks"

headers = {
    "Authorization": TOKEN,
    "Clientid": APPID,
    "companycode": COMPANY_CODE,
    "Accept": "application/json",
}
params = {"page": 1, "pageSize": 5}

r = requests.get(url, headers=headers, params=params, timeout=30)

print("URL:", url)
print("HTTP:", r.status_code)
print("CONTENT-TYPE:", r.headers.get("content-type"))
print(r.text[:3000])