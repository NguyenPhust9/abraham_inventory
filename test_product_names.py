"""Import parsing and the bounded legacy X6 data repair."""
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from product_names import split_model_color


class ProductNameTest(unittest.TestCase):
    def test_hyphenated_models_and_color_separators(self):
        cases = [
            ('X6-18 Vàng', ('X6-18', 'Vàng')),
            (' X6-20   Dương ', ('X6-20', 'Dương')),
            ('X6-18 Xanh dương', ('X6-18', 'Xanh dương')),
            ('X6-20 Đen Đỏ', ('X6-20', 'Đen Đỏ')),
            ('X6-18', ('X6-18', '')),
            ('X6-24 Có Đề', ('X6-24 Có Đề', '')),
            ('X6-24 Có Đề -  Vàng', ('X6-24 Có Đề', 'Vàng')),
            ('X6-18-Vàng', ('X6-18', 'Vàng')),
            ('AURA-20 - Cam', ('AURA-20', 'Cam')),
            ('PASSION 20 - CAM', ('PASSION 20', 'CAM')),
            ('MODEL - Màu tùy chỉnh', ('MODEL', 'Màu tùy chỉnh')),
            ('ABC-Pro', ('ABC-Pro', '')),
            ('Cốt Bạc Đạn 118MM', ('Cốt Bạc Đạn 118MM', '')),
            ('', ('', '')),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(split_model_color(value), expected)

    def test_migration_repairs_only_legacy_pairs_and_preserves_inventory(self):
        sql = (Path(__file__).parent / 'migrations' / '20261121_x6_model_names.sql').read_text(encoding='utf-8')
        with closing(sqlite3.connect(':memory:')) as db:
            db.executescript('''
                CREATE TABLE products (code TEXT PRIMARY KEY, model TEXT, color TEXT,
                    stock INTEGER, reserved INTEGER, price REAL, retail_price REAL,
                    image_filename TEXT, updated_at TEXT);
                CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            ''')
            for size in (18, 20):
                for color in ('Cam', 'Đỏ', 'Dương', 'Vàng'):
                    db.execute('INSERT INTO products VALUES (?, ?, ?, 36, 2, 1440000, 2000000, ?, ?)',
                               (f'X6-{size} {color}', 'X6', f'{size} {color}', 'keep.webp', 'before'))
            db.executemany('INSERT INTO products (code,model,color,updated_at) VALUES (?,?,?,?)', [
                ('X6-18 Lá', 'X6', '18 Lá', 'before'),
                ('X6-24 Có Đề - Vàng', 'X6-24 Có Đề', 'Vàng', 'before'),
                ('OTHER', 'X6', '18 Cam', 'before'),
            ])
            before = list(db.execute('SELECT * FROM products ORDER BY code'))
            db.executescript(sql)
            after = list(db.execute('SELECT * FROM products ORDER BY code'))
            self.assertEqual(sum(a != b for a, b in zip(before, after)), 8)
            for old, new in zip(before, after):
                if old != new:
                    self.assertEqual(new[:3], (old[0], old[0].split()[0], old[2][3:]))
                    self.assertEqual(new[3:8], old[3:8])
            db.executescript(sql)
            self.assertEqual(list(db.execute('SELECT * FROM products ORDER BY code')), after)
            # A manually changed color must not be overwritten on a later run.
            db.execute("UPDATE products SET model='X6',color='Custom' WHERE code='X6-18 Cam'")
            db.executescript(sql)
            self.assertEqual(db.execute("SELECT color FROM products WHERE code='X6-18 Cam'").fetchone()[0], 'Custom')


if __name__ == '__main__':
    unittest.main()
