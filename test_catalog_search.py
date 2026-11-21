"""Public catalog filtering, pagination and freshness on an isolated database."""
import importlib
import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


class CatalogSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///:memory:", "SUPABASE_POOLER_HOST": " ",
            "VERCEL": "1", "SECRET_KEY": "isolated-catalog-test",
        }):
            cls.web = importlib.import_module("app")
        assert cls.web.engine.url.get_backend_name() == "sqlite"
        assert cls.web.engine.url.database == ":memory:"

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.web.Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.factory = patch.object(self.web, "SessionLocal", self.sessions)
        self.factory.start()
        self.web._catalog_snapshots.clear()
        self.web.app.config.update(TESTING=True)
        self.client = self.web.app.test_client()
        with self.sessions() as db:
            db.add_all(self.web.Product(
                id=index, code=f"BIKE-{index:03}", model=f"A Bike {index:03}",
                category="Xe thể thao", color="Đen", stock=index * 2, reserved=1,
                price=index * 100, retail_price=index * 150, image_filename="bike.webp",
            ) for index in range(1, 36))
            db.add_all([
                self.web.Product(id=1000, code="CITY-RED", model="Đường phố Ánh Dương (tem mới)",
                                 category="Xe thành phố", color="Đỏ", stock=8, reserved=2,
                                 price=4000, retail_price=6000, image_filename="city.webp"),
                self.web.Product(id=1001, code="CITY-BLUE", model="Đường phố Ánh Dương (tem cũ)",
                                 category="Xe thành phố", color="Xanh", stock=12, reserved=2,
                                 price=5000, retail_price=7000, image_filename=""),
                self.web.Product(id=2000, code="NO-PHOTO", model="Without image", category="Hidden",
                                 color="Đỏ", stock=10, price=100, image_filename=""),
            ])
            db.commit()
        self.sql = []
        event.listen(self.engine, "before_cursor_execute", self.record_query)

    def record_query(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.sql.append(statement)

    def tearDown(self):
        self.factory.stop()
        self.web._catalog_snapshots.clear()
        self.engine.dispose()

    def get(self, **params):
        response = self.client.get("/api/products/dealer", query_string=params)
        self.assertEqual(response.status_code, 200)
        return response

    def setting(self, db, key, value):
        row = db.get(self.web.AppSetting, key)
        if row is None:
            db.add(self.web.AppSetting(key=key, value=value))
        else:
            row.value = value

    def batches(self):
        with self.sessions() as db:
            self.setting(db, "inventory_source", "batch")
            self.setting(db, "inventory_stock_id", "7")
            self.setting(db, "inventory_synced_at", "first")
            for product, key, quantity, reserved, days in (
                (1000, "a", 10, 3, 91), (1000, "b", 4, 4, 150), (1001, "c", 6, 2, 90),
            ):
                db.add(self.web.InventoryBatch(
                    stock_id=7, source_key=key, product_id=product, batch_number=f"LOT-{key}",
                    expiry_date=None, received_date=(date.today() - timedelta(days=days)).isoformat(),
                    quantity=quantity, reserved=reserved, source_json="{}", updated_at=datetime.now(),
                ))
            db.add(self.web.InventoryBatch(
                stock_id=8, source_key="other", product_id=1000, batch_number="OTHER",
                quantity=999, reserved=0, source_json="{}", updated_at=datetime.now(),
            ))
            db.commit()

    def test_search_finds_group_beyond_first_page_and_folds_vietnamese(self):
        first = self.get(page_size=24)
        self.assertNotIn(1000, [row["id"] for row in first.json])
        for query in ("DUONG do", "đường đỏ", "CITY-RED", "moi do duong"):
            with self.subTest(query=query):
                response = self.get(q=query, page_size=1)
                self.assertEqual([row["id"] for row in response.json], [1000])
                self.assertEqual(response.headers["X-Catalog-Total-Groups"], "1")
                self.assertEqual(response.headers["X-Catalog-Has-More"], "0")

    def test_pagination_keeps_normalized_group_and_shared_image_together(self):
        response = self.get(q="duong", page_size=1)
        self.assertEqual({row["id"] for row in response.json}, {1000, 1001})
        self.assertEqual({row["model"] for row in response.json}, {"Đường phố Ánh Dương"})
        self.assertEqual({row["image_url"] for row in response.json}, {"/static/uploads/city.webp"})
        self.assertEqual(response.headers["X-Catalog-Total-Rows"], "2")
        self.assertEqual(response.headers["X-Catalog-Total-Available"], "16")
        self.assertEqual(self.get(q="NO-PHOTO").json, [])

    def test_stock_category_and_price_filters_run_before_pagination(self):
        with self.sessions() as db:
            db.get(self.web.Product, 1).stock = 0
            db.commit()
        response = self.get(only_stock=1, min_price=3400, max_price=4000, page_size=1)
        self.assertEqual([row["id"] for row in response.json], [34])
        self.assertEqual(response.headers["X-Catalog-Total-Groups"], "3")
        response = self.get(category="Xe thành phố", max_price=4500, only_stock=1)
        self.assertEqual([row["id"] for row in response.json], [1000])
        self.assertEqual(json.loads(response.headers["X-Catalog-Categories"]), ["Xe thành phố", "Xe thể thao"])
        self.assertEqual(self.get(q="BIKE-001", only_stock=1).json, [])
        self.assertEqual(len(self.get(q="BIKE-001").json), 1)

    def test_stock_and_price_sort_cover_the_entire_catalog(self):
        self.assertEqual(self.get(sort="desc", page_size=1).json[0]["id"], 35)
        self.assertEqual(self.get(sort="asc", page_size=1).json[0]["id"], 1)
        self.assertEqual(self.get(sort="price-desc", page_size=1).json[0]["model"], "Đường phố Ánh Dương")
        self.assertEqual(self.get(sort="price-asc", page_size=1).json[0]["id"], 1)
        self.assertEqual(self.get(sort="desc", page=1, page_size=1).json[0]["id"], 34)

    def test_promotions_use_current_effective_price_and_tags(self):
        with self.sessions() as db:
            for index, tag, active in ((1, "discount", True), (2, "hot", True), (3, "discount", False)):
                product = db.get(self.web.Product, index)
                product.promotion_price = 50
                product.promotion_tag = tag
                product.promotion_start = date.today() - timedelta(days=2)
                product.promotion_end = date.today() + timedelta(days=1 if active else -1)
            db.commit()
        discounts = self.get(promotion="discount", max_price=60)
        self.assertEqual([row["id"] for row in discounts.json], [1])
        self.assertEqual((discounts.json[0]["price"], discounts.json[0]["original_price"]), (50, 100))
        self.assertEqual([row["id"] for row in self.get(promotion="all").json], [1, 2])
        self.assertEqual(self.get(q="BIKE-003").json[0]["price"], 300)

    def test_hidden_retail_never_returns_cached_products(self):
        self.get()
        hidden = self.client.get("/api/products/retail")
        self.assertEqual(hidden.json, [])
        self.assertEqual(hidden.headers["X-Retail-Prices-Visible"], "0")
        with self.sessions() as db:
            self.setting(db, "retail_prices_visible", "1")
            db.commit()
        visible = self.client.get("/api/products/retail", query_string={"q": "CITY-RED"})
        self.assertEqual(visible.json[0]["price"], 6000)
        self.assertFalse(visible.json[0]["promotion_active"])
        with self.sessions() as db:
            self.setting(db, "retail_prices_visible", "0")
            db.commit()
        self.assertEqual(self.client.get("/api/products/retail").json, [])

    def test_promotion_and_overdue_dates_use_vietnam_day_on_utc_servers(self):
        self.batches()
        vietnam_day = date(2026, 11, 22)
        with self.sessions() as db:
            product = db.get(self.web.Product, 1000)
            product.promotion_start = product.promotion_end = vietnam_day
            product.promotion_price = 10
            product.promotion_tag = "discount"
            db.get(self.web.InventoryBatch, (7, "a")).received_date = (vietnam_day - timedelta(days=91)).isoformat()
            db.commit()
        utc_now = datetime(2026, 11, 21, 18, 30, tzinfo=timezone.utc)
        with patch.object(self.web, "datetime") as clock:
            clock.now.side_effect = lambda tz=None: utc_now.astimezone(tz) if tz else utc_now.replace(tzinfo=None)
            response = self.get(q="CITY-RED", promotion="discount", overdue=1)
        self.assertEqual([row["row_id"] for row in response.json], ["1000:a"])
        self.assertEqual(response.json[0]["price"], 10)

    def test_warm_search_reads_only_revision_and_product_edits_invalidate(self):
        first = self.get(q="CITY-RED")
        self.assertEqual(len(self.sql), 2)
        self.sql.clear()
        self.get(q="BIKE-035", only_stock=1, sort="price-desc")
        self.assertEqual(len(self.sql), 1)
        self.assertIn("app_settings", self.sql[0])
        with self.sessions() as db:
            db.get(self.web.Product, 1000).stock = 22
            db.commit()
        changed = self.get(q="CITY-RED")
        self.assertEqual(changed.json[0]["available"], 20)
        self.assertNotEqual(first.headers["X-Catalog-Cache-Version"], changed.headers["X-Catalog-Cache-Version"])
        self.assertEqual(changed.headers["Cache-Control"], "no-store")

    def test_batch_rows_keep_metadata_and_use_lot_quantities(self):
        self.batches()
        response = self.get(only_stock=1)
        self.assertEqual({row["row_id"] for row in response.json}, {"1000:a", "1001:c"})
        self.assertEqual(response.headers["X-Catalog-Total-Groups"], "1")
        self.assertEqual(response.headers["X-Catalog-Total-Available"], "11")
        self.assertEqual(self.get(q="duong do", only_stock=1).json[0]["batch_number"], "LOT-a")
        self.assertEqual(len(self.get().json), 3)

    def test_batch_sync_timestamp_invalidates_without_product_revision(self):
        self.batches()
        self.get()
        with self.sessions() as db:
            db.get(self.web.InventoryBatch, (7, "a")).quantity = 20
            self.setting(db, "inventory_synced_at", "second")
            db.commit()
        self.assertEqual(self.get(q="CITY-RED", only_stock=1).json[0]["available"], 17)

    def test_overdue_filter_excludes_empty_lots_and_exactly_ninety_days(self):
        self.batches()
        response = self.get(overdue=1)
        self.assertEqual([row["row_id"] for row in response.json], ["1000:a"])
        self.assertEqual(response.headers["X-Catalog-Total-Available"], "7")
        self.assertEqual(self.get(overdue=1, q="CITY-BLUE").json, [])

    def test_invalid_and_out_of_range_parameters_are_bounded(self):
        response = self.get(page="bad", page_size="bad", min_price="nan", max_price="inf")
        self.assertEqual(response.headers["X-Catalog-Page"], "0")
        self.assertEqual(response.headers["X-Catalog-Page-Size"], "24")
        response = self.get(page_size=99999, page=-10)
        self.assertEqual(response.headers["X-Catalog-Page-Size"], "60")
        self.assertEqual(response.headers["X-Catalog-Total-Groups"], "36")
        response = self.get(page=99999)
        self.assertEqual(response.json, [])
        self.assertEqual(response.headers["X-Catalog-Has-More"], "0")
        self.assertEqual(self.get(min_price=5000, max_price=100).json, [])
        self.assertEqual(self.client.get("/api/products/invalid").status_code, 404)


if __name__ == "__main__":
    unittest.main()
