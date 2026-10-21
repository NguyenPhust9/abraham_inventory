import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from sqlalchemy import create_engine, text

import sync_amis_to_supabase as sync


class SyncAmisToSupabaseTest(unittest.TestCase):
    def setUp(self):
        handle, self.database_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.database_url = f"sqlite:///{self.database_path}"
        self.original_database_url = sync.DATABASE_URL
        sync.DATABASE_URL = self.database_url

        engine = create_engine(self.database_url)

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code VARCHAR UNIQUE NOT NULL,
                        model VARCHAR NOT NULL,
                        color VARCHAR DEFAULT '',
                        category VARCHAR DEFAULT '',
                        unit VARCHAR DEFAULT 'Chiếc',
                        stock INTEGER DEFAULT 0,
                        reserved INTEGER DEFAULT 0,
                        price FLOAT,
                        image_filename VARCHAR DEFAULT '',
                        amis_async_id VARCHAR,
                        updated_at DATETIME
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE product_lots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_id INTEGER NOT NULL,
                        stock_id INTEGER NOT NULL,
                        batch_number VARCHAR NOT NULL,
                        expiry_date DATETIME,
                        quantity INTEGER NOT NULL DEFAULT 0,
                        amis_product_async_id VARCHAR,
                        updated_at DATETIME,
                        UNIQUE (product_id, stock_id, batch_number)
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    INSERT INTO products (code, model, color, stock, reserved)
                    VALUES ('AURA-20 - Cam', 'AURA-20', 'Cam', 1, 0)
                    """
                )
            )

        engine.dispose()

    def tearDown(self):
        sync.DATABASE_URL = self.original_database_url
        os.remove(self.database_path)

    def test_updates_existing_and_inserts_new_product_once(self):
        inventory_map = sync.build_inventory_map(
            [
                {
                    "product_code": "AURA-20 - Cam",
                    "product_name": "AURA-20 - Cam",
                    "main_stock_quantity": 8,
                    "amount_summary": 2,
                },
                {
                    "product_code": "PASSION 20 - CAM",
                    "product_name": "PASSION 20 - CAM",
                    "main_stock_quantity": 12,
                    "amount_summary": 3,
                    "unit_name": "Chiếc",
                },
            ]
        )

        first_output = io.StringIO()
        second_output = io.StringIO()

        with redirect_stdout(first_output):
            sync.update_supabase(inventory_map)

        with redirect_stdout(second_output):
            sync.update_supabase(inventory_map)

        engine = create_engine(self.database_url)

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT code, model, color, stock, reserved
                    FROM products
                    ORDER BY code
                    """
                )
            ).mappings().all()

        engine.dispose()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["stock"], 8)
        self.assertEqual(rows[0]["reserved"], 2)
        self.assertEqual(rows[1]["code"], "PASSION 20 - CAM")
        self.assertEqual(rows[1]["model"], "PASSION 20")
        self.assertEqual(rows[1]["color"], "CAM")
        self.assertEqual(rows[1]["stock"], 12)
        self.assertEqual(rows[1]["reserved"], 3)
        self.assertIn(
            "GHI CHÚ: Đã thêm mới 1 mã hàng từ AMIS.",
            first_output.getvalue(),
        )
        self.assertNotIn("GHI CHÚ:", second_output.getvalue())

    def test_ignores_receipt_symbol_records(self):
        inventory_map = sync.build_inventory_map(
            [
                {
                    "product_code": "PT-HCM1",
                    "product_name": "Phiếu Thu Ký Hiệu: HCM 1",
                    "main_stock_quantity": 10,
                }
            ]
        )

        self.assertEqual(inventory_map, {})

    def test_builds_and_replaces_product_lots(self):
        batch_map = sync.build_batch_map(
            [
                {
                    "ProductCode": "AURA-20 - Cam",
                    "AsyncID": "product-uuid",
                    "StockID": 19,
                    "BatchNumber": "15092026",
                    "ExpiryDate": "2027-01-15T00:00:00+07:00",
                    "StockQuantitySummary": 3,
                },
                {
                    "ProductCode": "AURA-20 - Cam",
                    "AsyncID": "product-uuid",
                    "StockID": 19,
                    "BatchNumber": "15092026",
                    "StockQuantitySummary": 2,
                },
                {
                    "ProductCode": "AURA-20 - Cam",
                    "StockID": 19,
                    "BatchNumber": None,
                    "StockQuantitySummary": 8,
                },
            ]
        )

        self.assertEqual(len(batch_map), 1)
        self.assertEqual(next(iter(batch_map.values()))["quantity"], 5)

        sync.update_product_lots(batch_map, 19)

        engine = create_engine(self.database_url)
        with engine.connect() as connection:
            lot = connection.execute(
                text(
                    """
                    SELECT batch_number, quantity, amis_product_async_id
                    FROM product_lots
                    """
                )
            ).mappings().one()
            product_async_id = connection.execute(
                text("SELECT amis_async_id FROM products")
            ).scalar_one()
        engine.dispose()

        self.assertEqual(lot["batch_number"], "15092026")
        self.assertEqual(lot["quantity"], 5)
        self.assertEqual(lot["amis_product_async_id"], "product-uuid")
        self.assertEqual(product_async_id, "product-uuid")


if __name__ == "__main__":
    unittest.main()
