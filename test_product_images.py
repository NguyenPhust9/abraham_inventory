"""Image pipeline and real Flask routes, isolated from every configured database."""
import importlib
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine, event, func, select
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
        media._clear_image_response_cache()
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
        media._clear_image_response_cache()
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

    def test_media_uses_one_query_and_metadata_only_for_head_or_not_modified(self):
        self.login()
        self.upload()
        full_url = self.saved_url()
        statements = []

        def record_query(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_query)
        try:
            for variant in ("full", "thumb"):
                url = full_url.replace("full.webp", f"{variant}.webp")
                statements.clear()
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(statements), 1)
                self.assertIn(f"product_images.{variant}_data", statements[0])
                other_variant = "thumb" if variant == "full" else "full"
                self.assertNotIn(f"product_images.{other_variant}_data", statements[0])
                self.assertEqual(len(response.data), response.content_length)
                etag = response.headers["ETag"]

                for method, headers, status in (
                    ("HEAD", {}, 200),
                    ("GET", {"If-None-Match": etag}, 304),
                    ("GET", {"If-None-Match": "W/" + etag}, 304),
                ):
                    with self.subTest(variant=variant, method=method, headers=headers):
                        media._clear_image_response_cache()
                        statements.clear()
                        cached = self.client.open(url, method=method, headers=headers)
                        self.assertEqual(cached.status_code, status)
                        self.assertEqual(cached.data, b"")
                        self.assertEqual(len(statements), 1)
                        self.assertNotIn("full_data", statements[0])
                        self.assertNotIn("thumb_data", statements[0])
                        self.assertIn(f"product_images.{variant}_size", statements[0])
                        self.assertIn("immutable", cached.headers["Cache-Control"])

            statements.clear()
            missing_digest = "0" * 64
            missing = self.client.get(f"/media/products/{missing_digest}/full.webp", headers={
                "If-None-Match": f'"{missing_digest}-full"',
            })
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.headers["Cache-Control"], "no-store")
            self.assertEqual(len(statements), 1)
            self.assertNotIn("full_data", statements[0])
        finally:
            event.remove(self.engine, "before_cursor_execute", record_query)

    def test_warm_images_skip_database_for_get_head_and_conditional_requests(self):
        self.login()
        self.upload()
        full_url = self.saved_url()
        statements = []

        def record_query(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_query)
        try:
            for variant in ("full", "thumb"):
                url = full_url.replace("full.webp", f"{variant}.webp")
                cold = self.client.get(url)
                self.assertEqual(cold.status_code, 200)
                statements.clear()
                for method, headers, status in (
                    ("GET", {}, 200),
                    ("HEAD", {}, 200),
                    ("GET", {"If-None-Match": cold.headers["ETag"]}, 304),
                    ("GET", {"If-None-Match": "W/" + cold.headers["ETag"]}, 304),
                ):
                    with self.subTest(variant=variant, method=method, status=status):
                        warm = self.client.open(url, method=method, headers=headers)
                        self.assertEqual(warm.status_code, status)
                        self.assertEqual(warm.data, cold.data if method == "GET" and status == 200 else b"")
                        self.assertEqual(warm.headers["ETag"], cold.headers["ETag"])
                        self.assertIn("immutable", warm.headers["Cache-Control"])
                        if status == 200:
                            self.assertEqual(warm.content_length, len(cold.data))
                        self.assertEqual(statements, [])
        finally:
            event.remove(self.engine, "before_cursor_execute", record_query)

    def test_image_cache_evicts_by_bytes_and_entries_without_changing_responses(self):
        self.login()
        self.upload()
        full_url = self.saved_url()
        thumb_url = full_url.replace("full.webp", "thumb.webp")
        full = self.client.get(full_url).data
        thumb = self.client.get(thumb_url).data
        self.upload(data=picture("blue"))
        second_url = self.saved_url()
        statements = []

        def record_query(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_query)
        try:
            with patch.object(media, "IMAGE_RESPONSE_CACHE_ENTRIES", 2):
                media._clear_image_response_cache()
                self.client.get(full_url)
                self.client.get(thumb_url)
                self.client.get(full_url)  # Mark full as most recently used.
                self.client.get(second_url)
                statements.clear()
                self.assertEqual(self.client.get(full_url).data, full)
                self.assertEqual(statements, [])
                self.assertEqual(self.client.get(thumb_url).data, thumb)
                self.assertEqual(len(statements), 1)
                self.assertEqual(len(media._image_response_cache), 2)

            with patch.object(media, "IMAGE_RESPONSE_CACHE_BYTES", len(full) + len(thumb) - 1):
                media._clear_image_response_cache()
                statements.clear()
                for url, expected in ((full_url, full), (thumb_url, thumb), (full_url, full)):
                    self.assertEqual(self.client.get(url).data, expected)
                    self.assertLessEqual(media._image_response_cache_bytes, media.IMAGE_RESPONSE_CACHE_BYTES)
                self.assertEqual(len(statements), 3)

            with patch.object(media, "IMAGE_RESPONSE_CACHE_BYTES", len(full) - 1):
                media._clear_image_response_cache()
                statements.clear()
                self.assertEqual(self.client.get(full_url).data, full)
                self.assertEqual(self.client.get(full_url).data, full)
                self.assertEqual(len(statements), 2)
                self.assertEqual(media._image_response_cache_bytes, 0)
        finally:
            event.remove(self.engine, "before_cursor_execute", record_query)

    def test_image_cache_cannot_leak_across_database_binds(self):
        self.login()
        self.upload()
        url = self.saved_url()
        cached = self.client.get(url)
        other_engine = create_engine("sqlite:///:memory:")
        try:
            media.image_metadata.create_all(other_engine)
            with patch.object(self.web, "SessionLocal", sessionmaker(bind=other_engine)):
                response = self.client.get(url, headers={"If-None-Match": cached.headers["ETag"]})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(self.client.get(url).data, cached.data)
        finally:
            other_engine.dispose()

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
