"""Image pipeline and real Flask routes, isolated from every configured database."""
import importlib
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from werkzeug.datastructures import FileStorage

import product_images as media


def picture(color="orange", size=(1600, 1000), format="PNG"):
    data = BytesIO()
    Image.new("RGB", size, color).save(data, format=format)
    return data.getvalue()


class ProductImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The whitespace host prevents the local env loader from filling the real pooler.
        with patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///:memory:", "SUPABASE_POOLER_HOST": " ",
            "VERCEL": "1", "SECRET_KEY": "isolated-image-test-secret",
        }):
            cls.web = importlib.import_module("app")
        assert cls.web.engine.url.get_backend_name() == "sqlite"
        assert cls.web.engine.url.database == ":memory:"

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.web.Base.metadata.create_all(self.engine)
        media.image_metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.factory = patch.object(self.web, "SessionLocal", self.sessions)
        self.factory.start()
        self.web.app.config.update(TESTING=True)
        self.client = self.web.app.test_client()
        self.legacy = "https://res.cloudinary.com/desf1gsdl/image/upload/v1/products/old.jpg"
        with self.sessions() as db:
            db.add_all([
                self.web.Product(id=1, code="BIKE-ORANGE", model="Bike", color="Cam",
                                 category="Xe đạp 24", stock=5, price=100, image_filename=self.legacy),
                self.web.Product(id=2, code="BIKE-BLUE", model="Bike", color="Dương",
                                 category="Xe đạp 24", stock=8, price=200, image_filename=""),
            ])
            db.commit()
        self.image = picture()

    def tearDown(self):
        self.factory.stop()
        self.engine.dispose()

    def login(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = "admin"
            session["_fresh"] = True

    def upload(self, product=1, data=None):
        return self.client.post(f"/admin/products/{product}/image", data={
            "image": (BytesIO(self.image if data is None else data), "photo.png"),
        }, content_type="multipart/form-data")

    def saved_url(self, product=1):
        with self.sessions() as db:
            return db.get(self.web.Product, product).image_filename

    def count_blobs(self):
        with self.sessions() as db:
            return db.execute(select(func.count()).select_from(media.product_images)).scalar()

    def test_decode_limits_orientation_and_private_metadata(self):
        original = Image.new("RGB", (2000, 1000), "orange")
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private metadata"
        stream = BytesIO()
        original.save(stream, "JPEG", exif=exif)
        stream.seek(0)
        prepared = media.prepare_product_image(FileStorage(stream=stream, filename="photo.jpg"))
        self.assertLessEqual(prepared["full_size"], media.MAX_FULL_BYTES)
        self.assertLessEqual(prepared["thumb_size"], media.MAX_THUMB_BYTES)
        with Image.open(BytesIO(prepared["full_data"])) as result:
            self.assertEqual(result.format, "WEBP")
            self.assertLessEqual(max(result.size), 1280)
            self.assertGreater(result.height, result.width)
            self.assertFalse(result.getexif())
        with Image.open(BytesIO(prepared["thumb_data"])) as result:
            self.assertLessEqual(max(result.size), 480)

    def test_unauthenticated_upload_cannot_mutate(self):
        response = self.upload()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)
        self.assertEqual(self.saved_url(), self.legacy)
        self.assertEqual(self.count_blobs(), 0)

    def test_upload_deduplicates_and_preserves_inventory(self):
        self.login()
        self.assertEqual(self.upload().status_code, 302)
        url = self.saved_url()
        self.assertTrue(media.MEDIA_PATTERN.fullmatch(url))
        self.upload(product=2)
        self.assertEqual(self.saved_url(2), url)
        self.assertEqual(self.count_blobs(), 1)
        with self.sessions() as db:
            self.assertEqual((db.get(self.web.Product, 1).stock, db.get(self.web.Product, 1).price), (5, 100))

    def test_media_get_head_conditional_and_not_found(self):
        self.login()
        self.upload()
        url = self.saved_url()
        get = self.client.get(url)
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.mimetype, "image/webp")
        self.assertIn("immutable", get.headers["Cache-Control"])
        self.assertEqual(get.headers["X-Content-Type-Options"], "nosniff")
        head = self.client.head(url)
        self.assertEqual(head.data, b"")
        self.assertEqual(head.content_length, len(get.data))
        self.assertEqual(self.client.get(url, headers={"If-None-Match": get.headers["ETag"]}).status_code, 304)
        thumb = self.client.get(url.replace("full.webp", "thumb.webp"))
        self.assertEqual(thumb.status_code, 200)
        self.assertNotEqual(thumb.headers["ETag"], get.headers["ETag"])
        missing = self.client.get("/media/products/" + "0" * 64 + "/full.webp")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get(url.replace("full.webp", "huge.webp")).status_code, 404)

    def test_corrupt_unsupported_and_oversized_files_keep_old_image(self):
        self.login()
        for data in (b"not an image", picture(format="GIF"), b"x" * (media.MAX_UPLOAD_BYTES + 1)):
            with self.subTest(size=len(data)):
                self.upload(data=data)
                self.assertEqual(self.saved_url(), self.legacy)
                self.assertEqual(self.count_blobs(), 0)
        with patch.object(media, "MAX_IMAGE_PIXELS", 100):
            self.upload()
        self.assertEqual(self.saved_url(), self.legacy)

    def test_storage_budget_is_bounded_but_duplicate_is_allowed(self):
        self.login()
        self.upload()
        url = self.saved_url()
        with patch.object(media, "IMAGE_STORAGE_BUDGET", 1):
            self.upload(product=2)  # identical bytes consume no extra quota
            self.assertEqual(self.saved_url(2), url)
            self.upload(data=picture("blue"))
        self.assertEqual(self.saved_url(), url)
        self.assertEqual(self.count_blobs(), 1)

    def test_commit_failure_rolls_back_image_and_product_together(self):
        self.login()
        with patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("simulated commit failure")):
            self.upload()
        self.assertEqual(self.saved_url(), self.legacy)
        self.assertEqual(self.count_blobs(), 0)

    def test_shared_image_survives_unlink_and_product_deletion(self):
        self.login()
        self.upload()
        self.upload(product=2)
        url = self.saved_url()
        self.client.post("/admin/products/1/delete-image")
        self.assertEqual(self.saved_url(), "")
        self.assertEqual(self.saved_url(2), url)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post("/admin/products/1/delete")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_catalog_preserves_groups_without_leaking_blocked_urls(self):
        before = self.client.get("/api/products/dealer")
        self.assertEqual(len(before.json), 2)
        self.assertEqual(before.headers["X-Catalog-Total-Groups"], "1")
        self.assertTrue(all(row["image_url"] is None for row in before.json))
        self.assertNotIn("cloudinary", before.get_data(as_text=True))
        self.login()
        self.upload(product=2)
        after = self.client.get("/api/products/dealer")
        self.assertEqual(len(after.json), 2)
        self.assertTrue(all(row["image_url"] == self.saved_url(2) for row in after.json))
        self.assertTrue(all(row["image_thumb_url"].endswith("/thumb.webp") for row in after.json))
        self.assertNotEqual(before.headers["X-Catalog-Cache-Version"], after.headers["X-Catalog-Cache-Version"])

    def test_reorder_missing_images_does_not_remove_suggestions(self):
        with patch.object(self.web, "load_monthly_sales", return_value={"bike": 20}):
            response = self.client.get("/api/reorder-suggestions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["items"]), 1)
        self.assertIsNone(response.json["items"][0]["image_url"])
        self.assertNotIn("cloudinary", response.get_data(as_text=True))

    def test_dashboard_renders_new_image_form(self):
        self.login()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Lưu riêng ảnh", html)
        self.assertIn("/admin/products/1/image", html)
        self.assertNotIn(self.legacy, html)

    def test_invalid_edit_keeps_all_old_product_fields(self):
        self.login()
        self.client.post("/admin/products/1/edit", data={
            "code": "CHANGED", "model": "New", "stock": "999", "price": "999",
            "image": (BytesIO(b"broken"), "broken.png"),
        }, content_type="multipart/form-data")
        with self.sessions() as db:
            product = db.get(self.web.Product, 1)
            self.assertEqual((product.code, product.model, product.stock, product.price, product.image_filename),
                             ("BIKE-ORANGE", "Bike", 5, 100, self.legacy))

    def test_invalid_add_does_not_leave_product_row(self):
        self.login()
        self.client.post("/admin/products/add", data={
            "code": "NEW", "model": "New", "image": (BytesIO(b"broken"), "broken.png"),
        }, content_type="multipart/form-data")
        with self.sessions() as db:
            self.assertEqual(db.query(self.web.Product).count(), 2)

    def test_resolver_rejects_disabled_and_unsafe_references(self):
        for value in (self.legacy, "//evil.example/image", "javascript:alert(1)", "../secret", "/etc/passwd", "https://[invalid"):
            self.assertIsNone(media.resolve_product_image(value))
        self.assertEqual(media.resolve_product_image("old.jpg"), "/static/uploads/old.jpg")
        self.assertEqual(media.resolve_product_image("/images/products/photo.webp"), "/images/products/photo.webp")


if __name__ == "__main__":
    unittest.main()
