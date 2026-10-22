"""Validated per-ledger inventory snapshots, joined to existing product master data."""
import argparse
import copy
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from amis_app_session import AmisAppSession
import requests

CONFIG_PATH = Path(__file__).with_name(".env.amis-batch-request.json")


metadata = MetaData()
inventory_batches = Table(
    "inventory_batches", metadata,
    Column("stock_id", Integer, primary_key=True),
    Column("source_key", String, primary_key=True),
    Column("product_id", Integer, nullable=False, index=True),
    Column("batch_number", String, nullable=True),
    Column("expiry_date", String, nullable=True),
    Column("received_date", String, nullable=True),
    Column("quantity", Integer, nullable=False),
    Column("reserved", Integer, nullable=False),
    Column("source_json", String, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


def prepare_rows(rows):
    result = {}
    for row in rows:
        if not row.get("ProductCode") or not row.get("StockID"):
            raise ValueError("Dong ton kho thieu ma hang hoac kho; khong cap nhat snapshot.")
        quantity = float(row.get("StockQuantitySummary") or 0)
        reserved = row.get("DeliveryQuantity")
        if reserved is None:
            reserved = float(row.get("QuantitySummary") or 0) - float(row.get("ShippingAmountSummary") or 0)
        if not quantity.is_integer() or not float(reserved).is_integer():
            raise ValueError("Ton kho co so luong le; can doi kieu du lieu truoc khi dong bo.")
        # User's business convention: CRM ExpiryDate is displayed as receipt date.
        received = row.get("ExpiryDate") or None
        identity = [row["ProductCode"], row.get("LedgerID"), row.get("BatchNumber"), row.get("ExpiryDate")]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        record = dict(stock_id=int(row["StockID"]), source_key=key,
                      code=str(row["ProductCode"]).strip(), batch_number=row.get("BatchNumber") or None,
                      expiry_date=row.get("ExpiryDate") or None, received_date=received,
                      quantity=int(quantity), reserved=max(0, int(reserved)),
                      source_json=json.dumps(row, ensure_ascii=False), updated_at=datetime.utcnow())
        identifier = (record["stock_id"], key)
        if identifier in result:
            raise ValueError("API tra trung dong so cai; khong cong don de tranh sai ton.")
        result[identifier] = record
    return list(result.values())


def fetch_snapshot(har_path, session):
    request = read_template(har_path)
    template = json.loads(request["postData"]["text"])
    stock = next(int(f["Value"]) for f in template["Filters"] if f["Property"] == "StockID")
    rows, total, seen = [], None, set()
    for page in range(1, 1001):
        payload = copy.deepcopy(template)
        payload.update(Page=page, PageSize=100, Start=(page - 1) * 100, IsGetCache=False)
        response = session.request("POST", request["url"], json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("Success") is not True or not isinstance(data.get("Data"), list):
            raise ValueError("AMIS khong tra snapshot hop le.")
        if total is None:
            total = int(data["Total"])
        elif int(data["Total"]) != total:
            raise ValueError("So dong thay doi trong luc lay du lieu; thu lai lan sau.")
        batch = data["Data"]
        fingerprint = json.dumps(batch, sort_keys=True)
        if batch and fingerprint in seen:
            raise ValueError("API lap trang; khong ghi database.")
        seen.add(fingerprint)
        rows.extend(batch)
        print(f"Trang {page}: {len(rows)}/{total}", flush=True)
        if len(rows) >= total or not batch:
            break
    if len(rows) != total or any(int(r.get("StockID") or 0) != stock for r in rows):
        raise ValueError("Snapshot chua du hoac sai kho; giu nguyen du lieu cu.")
    return stock, rows


def read_template(path):
    content = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if "log" not in content:
        request = content
    else:
        entry = next((e for e in reversed(content["log"]["entries"]) if "/Stock/productLedgerBatch/Paging" in e["request"]["url"]), None)
        if not entry:
            raise ValueError("HAR khong co request ton theo lo.")
        request = entry["request"]
    if request["url"].split("?")[0] != "https://amisapp.misa.vn/crm/g1/api/business/Stock/productLedgerBatch/Paging":
        raise ValueError("Sai endpoint ton kho theo lo.")
    return {"url": request["url"], "postData": {"text": request["postData"]["text"]}}


def sync_configured_snapshot():
    from sync_amis_to_supabase import DATABASE_URL
    stock, rows = fetch_snapshot(CONFIG_PATH, AmisAppSession())
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        apply_snapshot(engine, stock, rows, backup_dir=Path(__file__).parent / "data" / "inventory_backups")
    finally:
        engine.dispose()


def apply_snapshot(engine, stock_id, source_rows, backup_dir=None):
    from sync_amis_to_supabase import normalize_code, split_model_color
    rows = prepare_rows(source_rows)
    if any(r["stock_id"] != stock_id for r in rows):
        raise ValueError("Snapshot co dong thuoc kho khac.")
    metadata.create_all(engine)
    with engine.begin() as connection:
        mode = connection.execute(text("SELECT value FROM app_settings WHERE key='inventory_source'")).scalar()
        if backup_dir is not None and mode != "batch":
            backup = {
                "products": [dict(r) for r in connection.execute(text("SELECT id,code,stock,reserved FROM products")).mappings()],
                "settings": [dict(r) for r in connection.execute(text("SELECT key,value FROM app_settings WHERE key IN ('inventory_source','inventory_stock_id','inventory_synced_at')")).mappings()],
            }
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / (datetime.now().strftime("before_batch_%Y%m%d_%H%M%S") + ".json")
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
        products = connection.execute(text("SELECT id, code FROM products")).mappings().all()
        by_code = {normalize_code(p["code"]): p["id"] for p in products}
        totals = {}
        inserts = []
        for row in rows:
            code = normalize_code(row["code"])
            product_id = by_code.get(code)
            if product_id is None:
                source = json.loads(row["source_json"])
                model, color = split_model_color(source.get("ProductName") or row["code"])
                connection.execute(text("INSERT INTO products (code, model, color, category, unit, stock, reserved, updated_at) "
                    "VALUES (:code,:model,:color,:category,:unit,0,0,CURRENT_TIMESTAMP)"),
                    dict(code=row["code"], model=model or row["code"], color=color,
                         category=source.get("ProductCategoryIDText") or "",
                         unit=source.get("ConversionUnitIDText") or source.get("UsageUnitIDText") or "Chiếc"))
                product_id = connection.execute(text("SELECT id FROM products WHERE code=:code"), {"code": row["code"]}).scalar_one()
                by_code[code] = product_id
            quantities = totals.setdefault(product_id, [0, 0])
            quantities[0] += row["quantity"]
            quantities[1] += row["reserved"]
            inserts.append({k: v for k, v in dict(row, product_id=product_id).items() if k != "code"})
        # Metadata, totals and source selection commit as one transaction.
        connection.execute(inventory_batches.delete().where(inventory_batches.c.stock_id == stock_id))
        if inserts:
            connection.execute(inventory_batches.insert(), inserts)
        connection.execute(text("""
            UPDATE products SET
                stock=COALESCE((SELECT SUM(quantity) FROM inventory_batches
                    WHERE inventory_batches.product_id=products.id AND stock_id=:stock_id),0),
                reserved=COALESCE((SELECT SUM(reserved) FROM inventory_batches
                    WHERE inventory_batches.product_id=products.id AND stock_id=:stock_id),0),
                updated_at=CURRENT_TIMESTAMP
        """), {"stock_id": stock_id})
        for key, value in (("inventory_source", "batch"), ("inventory_stock_id", str(stock_id)),
                           ("inventory_synced_at", datetime.utcnow().isoformat())):
            connection.execute(text("DELETE FROM app_settings WHERE key=:key"), {"key": key})
            connection.execute(text("INSERT INTO app_settings (key,value) VALUES (:key,:value)"), {"key": key, "value": value})
    print(f"Da dong bo {len(rows)} dong lo, {len(totals)} ma hang.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--har", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Ghi snapshot va chuyen nguon hien thi sang theo lo.")
    args = parser.parse_args()
    try:
        stock, rows = fetch_snapshot(args.har, AmisAppSession())
        output = Path(__file__).parent / "data" / "amis_batch_preview.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        prepared = prepare_rows(rows)
        print(f"Hop le: {len(prepared)} dong; {sum(not r['batch_number'] for r in prepared)} dong khong co so lo; "
              f"{sum(bool(r['received_date']) for r in prepared)} dong co ngay nhap kho.")
        if args.apply:
            from sync_amis_to_supabase import DATABASE_URL
            engine = create_engine(DATABASE_URL, pool_pre_ping=True)
            try:
                apply_snapshot(engine, stock, rows, backup_dir=output.parent / "inventory_backups")
                template = read_template(args.har)
                temp_path = CONFIG_PATH.with_suffix(".tmp")
                temp_path.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
                os.replace(temp_path, CONFIG_PATH)
            finally:
                engine.dispose()
    except (OSError, ValueError, requests.RequestException, SQLAlchemyError) as error:
        print("LOI: " + (str(error) if isinstance(error, ValueError) else type(error).__name__))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
