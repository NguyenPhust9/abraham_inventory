"""Create the image table or export a consistent, portable image backup.

Does not import the web app, alter products, or delete image data.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


ROOT = Path(__file__).resolve().parent


def database_engine():
    env = dict(os.environ)
    for name in (".env.pooler", ".env.local", ".env"):
        path = ROOT / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if not env.get(key.strip()):
                        env[key.strip()] = value.strip()
    url = make_url(env.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1))
    if url.get_backend_name() != "postgresql":
        raise ValueError("This maintenance tool requires the configured PostgreSQL database.")
    host = env.get("SUPABASE_POOLER_HOST", "").strip()
    if host:
        user = url.username
        if user == "postgres" and (url.host or "").startswith("db."):
            user = "postgres." + url.host.split(".")[1]
        url = url.set(host=host, username=user, port=int(env.get("SUPABASE_POOLER_PORT", "5432")))
    return create_engine(url, poolclass=NullPool, connect_args={
        "connect_timeout": 15, "sslmode": "require", "options": "-c statement_timeout=30000",
    })


def export_backup(engine, destination):
    destination = Path(destination).resolve()
    # Never overwrite an earlier backup.
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "products": [], "images": []}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            manifest["products"] = [dict(row) for row in connection.execute(text(
                "SELECT id, code, model, color, image_filename FROM products ORDER BY id"
            )).mappings()]
            exists = connection.execute(text("SELECT to_regclass('public.product_images')")).scalar()
            if exists:
                rows = connection.execute(text(
                    "SELECT digest, full_data, thumb_data FROM product_images ORDER BY digest"
                )).mappings()
                for row in rows:
                    full, thumb = bytes(row["full_data"]), bytes(row["thumb_data"])
                    if hashlib.sha256(full + b"\0" + thumb).hexdigest() != row["digest"]:
                        raise ValueError("An image checksum failed; this backup is incomplete.")
                    folder = destination / row["digest"]
                    folder.mkdir()
                    (folder / "full.webp").write_bytes(full)
                    (folder / "thumb.webp").write_bytes(thumb)
                    manifest["images"].append({"digest": row["digest"], "full_size": len(full), "thumb_size": len(thumb)})
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(destination), "products": len(manifest["products"]),
                      "images": len(manifest["images"])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--init", action="store_true", help="Apply the additive PostgreSQL image-table migration.")
    action.add_argument("--backup", metavar="NEW_DIRECTORY", help="Export image bytes and all product references.")
    args = parser.parse_args()
    engine = database_engine()
    try:
        if args.init:
            sql = (ROOT / "migrations" / "20261120_product_images.sql").read_text(encoding="utf-8")
            with engine.begin() as connection:
                connection.exec_driver_sql(sql)
            print("Image table ready. Existing product references are unchanged.")
        else:
            export_backup(engine, args.backup)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
