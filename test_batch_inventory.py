import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from batch_inventory import apply_snapshot, prepare_rows


class BatchInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.engine = create_engine("sqlite:///" + str(Path(cls.temp.name) / "test.db"))
        # Import application against an isolated database; never connect to the configured live DB.
        with patch("sqlalchemy.create_engine", return_value=cls.engine):
            import app
        cls.web = app

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.temp.cleanup()

    def setUp(self):
        with self.engine.begin() as conn:
            for table in ("inventory_batches", "app_settings", "products"):
                conn.execute(text(f"DELETE FROM {table}"))
            conn.execute(text("INSERT INTO products (id,code,model,color,category,unit,stock,reserved,price,retail_price,image_filename) "
                              "VALUES (1,'AURA - Cam','AURA','Cam','Xe','Chiếc',99,5,100,150,'test.jpg')"))
        self.rows = [
            dict(ProductCode="AURA - Cam", StockID=19, LedgerID=1, BatchNumber="A", ExpiryDate="2026-09-01T00:00:00+07:00", StockQuantitySummary=5, QuantitySummary=2, ShippingAmountSummary=1),
            dict(ProductCode="AURA - Cam", StockID=19, LedgerID=2, BatchNumber="A", ExpiryDate="2026-10-01T00:00:00+07:00", StockQuantitySummary=7),
            dict(ProductCode="AURA - Cam", StockID=19, LedgerID=3, BatchNumber=None, ExpiryDate=None, StockQuantitySummary=3),
        ]

    def test_rows_with_same_code_keep_separate_dates_and_blank_batch(self):
        prepared = prepare_rows(self.rows)
        self.assertEqual(len(prepared), 3)
        self.assertEqual(prepared[0]["received_date"], self.rows[0]["ExpiryDate"])
        self.assertIsNone(prepared[2]["received_date"])
        self.assertIsNone(prepared[2]["batch_number"])
        apply_snapshot(self.engine, 19, self.rows)
        apply_snapshot(self.engine, 19, self.rows)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM inventory_batches")).scalar_one(), 3)
            master = conn.execute(text("SELECT stock,reserved,price,image_filename FROM products WHERE id=1")).mappings().one()
        self.assertEqual((master["stock"], master["reserved"], master["price"], master["image_filename"]), (15, 1, 100, "test.jpg"))
        with self.web.app.test_client() as client:
            response = client.get("/api/products/dealer")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(len(data), 3)
            self.assertEqual(len({r["row_id"] for r in data}), 3)
            self.assertEqual({r["code"] for r in data}, {"AURA - Cam"})
            self.assertEqual({r["price"] for r in data}, {100})
            self.assertEqual({r["image_url"] for r in data}, {"test.jpg"})
            self.assertEqual(sum(r["stock"] for r in data), 15)
            self.assertEqual(sum(r["available"] for r in data), 14)
            self.assertEqual(sum(r["received_date"] is None for r in data), 1)
            with self.engine.begin() as conn:
                conn.execute(text("INSERT INTO app_settings (key,value) VALUES ('retail_prices_visible','1')"))
            retail = client.get("/api/products/retail").get_json()
            self.assertEqual(len(retail), 3)
            self.assertEqual({r["price"] for r in retail}, {150})

    def test_unpictured_products_hidden_until_image_added(self):
        apply_snapshot(self.engine, 19, self.rows)
        with self.web.app.test_client() as client:
            for image in (None, "", "   "):
                with self.engine.begin() as conn:
                    conn.execute(text("UPDATE products SET image_filename=:image WHERE id=1"), {"image": image})
                self.assertEqual(client.get("/api/products/dealer").get_json(), [])
                with self.engine.connect() as conn:
                    self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM inventory_batches")).scalar_one(), 3)
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE products SET image_filename='restored.jpg' WHERE id=1"))
            self.assertEqual(len(client.get("/api/products/dealer").get_json()), 3)

    def test_one_image_keeps_all_codes_in_group(self):
        with self.engine.begin() as conn:
            for number in range(2, 6):
                conn.execute(text("INSERT INTO products (id,code,model,color,category,stock,reserved,image_filename) "
                                  "VALUES (:id,:code,'AURA (variant)','Other','Xe',4,0,'')"),
                             {"id": number, "code": f"AURA-{number}"})
            conn.execute(text("INSERT INTO products (id,code,model,category,stock,reserved,image_filename) "
                              "VALUES (6,'NO-IMAGE','OTHER','Xe',20,0,'')"))
            conn.execute(text("INSERT INTO products (id,code,model,category,stock,reserved,image_filename) "
                              "VALUES (7,'OTHER-CATEGORY','AURA','Other category',20,0,'')"))
        with self.web.app.test_client() as client:
            data = client.get("/api/products/dealer").get_json()
            self.assertEqual({item['id'] for item in data}, {1, 2, 3, 4, 5})
            self.assertEqual({item['image_url'] for item in data}, {'test.jpg'})
            self.assertEqual(sum(item['stock'] for item in data), 115)

    def test_invalid_snapshot_preserves_old_inventory(self):
        apply_snapshot(self.engine, 19, self.rows)
        with self.assertRaises(ValueError):
            apply_snapshot(self.engine, 19, self.rows + [self.rows[0]])
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT stock FROM products WHERE id=1")).scalar_one(), 15)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM inventory_batches")).scalar_one(), 3)

    def test_new_snapshot_removes_stale_rows(self):
        apply_snapshot(self.engine, 19, self.rows)
        apply_snapshot(self.engine, 19, self.rows[:1])
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM inventory_batches")).scalar_one(), 1)
            self.assertEqual(conn.execute(text("SELECT stock FROM products WHERE id=1")).scalar_one(), 5)


if __name__ == "__main__":
    unittest.main()
