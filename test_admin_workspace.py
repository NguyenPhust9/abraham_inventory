"""Admin workspaces and mutations using an isolated, in-memory database."""
import importlib
import json
import os
import re
import unittest
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pandas as pd
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


class AdminWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///:memory:", "SUPABASE_POOLER_HOST": " ",
            "VERCEL": "1", "SECRET_KEY": "isolated-admin-test",
        }):
            cls.web = importlib.import_module("app")
        assert cls.web.engine.url.get_backend_name() == "sqlite"
        assert cls.web.engine.url.database == ":memory:"

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.web.Base.metadata.create_all(self.engine)
        self.web.image_metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.factory = patch.object(self.web, "SessionLocal", self.sessions)
        self.factory.start()
        self.web.app.config.update(TESTING=True)
        self.client = self.web.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = "admin"
            session["_fresh"] = True
        with self.sessions() as db:
            for index in range(1, 62):
                db.add(self.web.Product(
                    id=index, code=f"BIKE-{index:03}", model=f"Bike {index:03}",
                    color="Đen", category="Xe đạp", unit="Bộ", stock=10, reserved=3,
                    price=1000000, retail_price=1200000, image_filename="",
                    promotion_price=900000 if index <= 31 else None,
                    promotion_start=date(2026, 1, 1) if index <= 31 else None,
                    promotion_end=date(2027, 1, 1) if index <= 31 else None,
                    updated_at=datetime(2026, 11, 1),
                ))
            db.commit()
        self.sql = []
        event.listen(self.engine, "before_cursor_execute", self.record_query)

    def record_query(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.sql.append(statement)

    def tearDown(self):
        self.factory.stop()
        self.engine.dispose()

    def get_html(self, path="/admin"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def editor_data(self, html):
        return json.loads(re.search(r'<script type="application/json" id="editorProducts">(.*?)</script>', html, re.S)[1])

    def test_products_only_fetch_the_page_and_use_one_editor(self):
        html = self.get_html()
        self.assertEqual(html.count('data-product-id="'), 10)
        self.assertEqual(html.count('<dialog '), 1)
        self.assertNotIn('id="promotionBatchForm"', html)
        self.assertNotIn('id="promotion-code-list"', html)
        self.assertNotIn('class="stats-grid"', html)
        self.assertEqual(len(self.sql), 3)  # count, ten rows, distinct categories
        product_selects = [sql for sql in self.sql if 'products.id AS products_id' in sql and 'count(' not in sql]
        self.assertEqual(len(product_selects), 1)
        self.assertIn('LIMIT', product_selects[0])
        self.assertEqual(len(self.editor_data(html)), 10)

    def test_search_pagination_and_editor_preserve_both_prices(self):
        html = self.get_html('/admin?q=Bike&price_type=retail&page=2')
        data = self.editor_data(html)
        self.assertEqual(data[0]['id'], 11)
        self.assertEqual(data[0]['price'], 1000000)
        self.assertEqual(data[0]['retail_price'], 1200000)
        self.assertEqual(data[0]['unit'], 'Bộ')
        self.assertIn('name="return_page" value="2"', html)
        self.assertIn('name="return_price_type" value="retail"', html)
        self.assertIn('name="return_q" value="Bike"', html)
        self.assertEqual(len(self.editor_data(self.get_html('/admin?q=BIKE-061'))), 1)
        self.assertIn('Không tìm thấy sản phẩm', self.get_html('/admin?q=missing'))

    def test_invalid_page_and_empty_inventory(self):
        self.assertEqual(self.editor_data(self.get_html('/admin?page=999'))[0]['id'], 61)
        for page in ['-3', 'bad']:
            self.assertEqual(self.editor_data(self.get_html('/admin?page=' + page))[0]['id'], 1)
        with self.sessions() as db:
            db.query(self.web.Product).delete()
            db.commit()
        html = self.get_html('/admin?page=3')
        self.assertIn('0 mã hàng', html)
        self.assertEqual(self.editor_data(html), [])
        self.assertIn('Tổng quan kho', self.get_html('/admin?section=overview'))

    def test_edit_and_image_actions_preserve_location(self):
        context = dict(return_q='Bike', return_page='2', return_price_type='retail')
        response = self.client.post('/admin/products/11/edit', data=dict(
            code='BIKE-011', model='Bike 011', color='Xanh', category='Xe đạp', unit='Bộ',
            stock='12', reserved='3', price='1000000', retail_price='1250000', **context))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parse_qs(urlparse(response.location).query),
                         {'q': ['Bike'], 'page': ['2'], 'price_type': ['retail']})
        with self.sessions() as db:
            product = db.get(self.web.Product, 11)
            self.assertEqual((product.color, product.stock, product.unit), ('Xanh', 12, 'Bộ'))
        for route in ['image', 'delete-image']:
            result = self.client.post('/admin/products/11/' + route, data=context)
            self.assertEqual(result.location, response.location)

    def test_delete_last_page_clamps_and_bad_return_values_are_safe(self):
        response = self.client.post('/admin/products/61/delete', data=dict(return_page=7))
        html = self.get_html(response.location)
        self.assertEqual(len(self.editor_data(html)), 10)
        self.assertIn('name="return_page" value="6"', html)
        response = self.client.post('/admin/products/999/delete', data=dict(
            return_page='bad', return_price_type='https://example.com', return_url='https://example.com'))
        self.assertTrue(response.location.startswith('/admin?'))
        self.assertEqual(parse_qs(urlparse(response.location).query)['price_type'], ['dealer'])

    def test_add_and_edit_accept_vnd_prices_without_rounding_to_thousands(self):
        cases = [
            ('1.000', '70.500', 1000, 70500),
            ('47.001', '1.234.567', 47001, 1234567),
            ('47000', '70501', 47000, 70501),
            ('47000.0', '70500.0', 47000, 70500),
            ('0', '', 0, None),
            ('', '0', None, 0),
        ]
        for index, (price, retail_price, expected_price, expected_retail) in enumerate(cases):
            for action in ['add', 'edit']:
                with self.subTest(action=action, price=price, retail_price=retail_price):
                    code = f'VND-{index}' if action == 'add' else 'BIKE-001'
                    route = '/admin/products/add' if action == 'add' else '/admin/products/1/edit'
                    response = self.client.post(route, data=dict(
                        code=code, model='Price test', stock='10', reserved='3',
                        price=price, retail_price=retail_price))
                    self.assertEqual(response.status_code, 302)
                    with self.sessions() as db:
                        product = db.query(self.web.Product).filter_by(code=code).one()
                        self.assertEqual(product.price, expected_price)
                        self.assertEqual(product.retail_price, expected_retail)

    def test_promotion_workspace_is_paginated_and_clear_all_is_global(self):
        html = self.get_html('/admin?section=promotions')
        self.assertEqual(html.count('class="promotion-edit"'), 25)
        self.assertIn('Gỡ tất cả (31)', html)
        self.assertNotIn('id="productEditor"', html)
        self.assertEqual(self.get_html('/admin?section=promotions&page=2').count('class="promotion-edit"'), 6)
        response = self.client.post('/admin/promotions/update', data={'action': 'clear_all'})
        self.assertIn('section=promotions', response.location)
        with self.sessions() as db:
            self.assertEqual(db.query(self.web.Product).filter(self.web.Product.promotion_price.isnot(None)).count(), 0)

    def test_promotion_save_and_excel_import_still_work(self):
        row = dict(code='BIKE-061', promotion_price=800000, promotion_tag='hot',
                   promotion_start='2026-11-01', promotion_end='2026-12-01')
        response = self.client.post('/admin/promotions/update', data={'promotions_json': json.dumps([row])})
        self.assertIn('section=promotions', response.location)
        with self.sessions() as db:
            self.assertEqual(db.get(self.web.Product, 61).promotion_price, 800000)
        file = BytesIO()
        pd.DataFrame([{'Mã hàng': 'BIKE-060', 'Giá khuyến mãi': 700000, 'Tag': 'hot',
                       'Áp dụng từ': '2026-11-01', 'Áp dụng tới': '2026-12-01'}]).to_excel(file, index=False)
        file.seek(0)
        response = self.client.post('/admin/promotions/import', data={'file': (file, 'promotions.xlsx')})
        self.assertIn('section=promotions', response.location)
        with self.sessions() as db:
            self.assertEqual(db.get(self.web.Product, 60).promotion_price, 700000)

    def test_other_sections_and_safe_embedded_data(self):
        for section, expected in [('import', 'Cập nhật giá'), ('add', 'Thêm sản phẩm mới'),
                                  ('overview', 'Cảnh báo tồn kho')]:
            self.assertIn(expected, self.get_html('/admin?section=' + section))
        self.assertIn('id="productEditor"', self.get_html('/admin?section=invalid'))
        with self.sessions() as db:
            db.get(self.web.Product, 1).color = '</script><script>alert(1)</script>'
            db.commit()
        html = self.get_html('/admin?q=BIKE-001')
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('</script>', self.editor_data(html)[0]['color'])

    def test_excel_import_keeps_x6_sizes_in_models_for_existing_and_new_products(self):
        with self.sessions() as db:
            existing = db.get(self.web.Product, 1)
            existing.code, existing.model, existing.color = 'X6-18 Vàng', 'X6', '18 Vàng'
            existing.image_filename = 'keep.webp'
            db.commit()
        rows = [
            {'Mã hàng hóa': 'X6-18 Vàng', 'Tên hàng hóa': 'X6-18 Vàng'},
            {'Mã hàng hóa': 'X6-20 Dương', 'Tên hàng hóa': 'X6-20 Dương'},
        ]
        file = BytesIO()
        pd.DataFrame(rows).to_excel(file, index=False)
        file.seek(0)
        response = self.client.post('/admin/import', data={'file': (file, 'products.xlsx')})
        self.assertEqual(response.status_code, 302)
        with self.sessions() as db:
            existing = db.get(self.web.Product, 1)
            self.assertEqual((existing.model, existing.color), ('X6-18', 'Vàng'))
            self.assertEqual((existing.stock, existing.reserved, existing.price,
                              existing.retail_price, existing.image_filename),
                             (10, 3, 1000000, 1200000, 'keep.webp'))
            added = db.query(self.web.Product).filter_by(code='X6-20 Dương').one()
            self.assertEqual((added.model, added.color), ('X6-20', 'Dương'))
            added.image_filename = 'new.webp'
            db.commit()
        for model, color in [('X6-18', 'Vàng'), ('X6-20', 'Dương')]:
            result = self.client.get('/api/products/dealer', query_string={'q': model})
            self.assertEqual(result.status_code, 200)
            self.assertEqual([(row['model'], row['color']) for row in result.json], [(model, color)])
        self.assertEqual(self.web.split_model_color('24BIKE Nhôm (tem đậm) - Đỏ'), ('24BIKE Nhôm', 'Đỏ'))

    def test_unauthenticated_sections_require_login(self):
        client = self.web.app.test_client()
        for path in ['/admin', '/admin?section=promotions', '/admin?section=import']:
            response = client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/admin/login', response.location)


if __name__ == '__main__':
    unittest.main()
