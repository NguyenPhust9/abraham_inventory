"""Small, bounded product-image store using the application's existing database.

Only this table contains image bytes; catalog queries continue to read URLs only.
Old blobs are retained when a product is edited/deleted so cached/shared URLs work.
The 100 MiB budget includes these retained blobs, not just current references.
"""
import hashlib
import re
import warnings
from collections import OrderedDict
from datetime import datetime
from io import BytesIO
from threading import Lock
from urllib.parse import quote, urlsplit

from flask import Response, request
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Column, DateTime, Integer, LargeBinary, MetaData, String, Table, func, select, text


MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_FULL_BYTES = 200 * 1024
MAX_THUMB_BYTES = 50 * 1024
IMAGE_STORAGE_BUDGET = 100 * 1024 * 1024
IMAGE_STORE_LOCK = 718304251
MEDIA_PATTERN = re.compile(r"^/media/products/([a-f0-9]{64})/(full|thumb)\.webp$")
# Image URLs are content addressed: replacing an image creates a different URL.
# Keep frequently viewed bytes close to the app instead of reading the remote
# database on every browser cache miss. Bound both bytes and entry overhead.
IMAGE_RESPONSE_CACHE_BYTES = 32 * 1024 * 1024
IMAGE_RESPONSE_CACHE_ENTRIES = 512
_image_response_cache = OrderedDict()
_image_response_cache_bytes = 0
_image_response_cache_lock = Lock()

image_metadata = MetaData()
product_images = Table(
    "product_images", image_metadata,
    Column("digest", String(64), primary_key=True),
    Column("full_data", LargeBinary, nullable=False),
    Column("thumb_data", LargeBinary, nullable=False),
    Column("full_size", Integer, nullable=False),
    Column("thumb_size", Integer, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)


class ProductImageError(ValueError):
    """A safe, actionable upload error that can be shown to an administrator."""


def resolve_product_image(value, thumbnail=False):
    """Resolve stored references without requesting the disabled image provider."""
    value = str(value or "").strip()
    if not value:
        return None
    media = MEDIA_PATTERN.fullmatch(value)
    if media:
        variant = "thumb" if thumbnail else "full"
        return f"/media/products/{media.group(1)}/{variant}.webp"
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if host == "cloudinary.com" or host.endswith(".cloudinary.com"):
        return None
    if parsed.scheme:
        return value if parsed.scheme in ("http", "https") and host else None
    if value.startswith("//") or ".." in value.split("/") or "\\" in value:
        return None
    if value.startswith(("/static/", "/images/")):
        return value
    if value.startswith("/"):
        return None
    return "/static/uploads/" + quote(value, safe="/")


def _encode_webp(image, edge, byte_limit):
    resized = image.copy()
    resized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    # Fixed sizes/qualities: no unbounded transformation variants.
    for _ in range(5):
        for quality in (82, 72, 62):
            output = BytesIO()
            resized.save(output, format="WEBP", quality=quality, method=4)
            data = output.getvalue()
            if len(data) <= byte_limit:
                return data, resized.size
        resized.thumbnail(
            (max(1, round(resized.width * .8)), max(1, round(resized.height * .8))),
            Image.Resampling.LANCZOS,
        )
    raise ProductImageError("Ảnh quá phức tạp để tối ưu. Vui lòng chọn ảnh nhỏ hơn.")


def prepare_product_image(file):
    if not file or not getattr(file, "filename", ""):
        return None
    data = file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ProductImageError("Ảnh tối đa 4 MB. Vui lòng chọn ảnh nhỏ hơn.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise ProductImageError("Chỉ nhận ảnh JPG, PNG hoặc WebP.")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ProductImageError("Ảnh tối đa 24 megapixel. Vui lòng giảm kích thước ảnh.")
                if getattr(source, "is_animated", False):
                    raise ProductImageError("Vui lòng chọn ảnh tĩnh JPG, PNG hoặc WebP.")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA")
                # Copy pixels into a new image so EXIF, ICC and other metadata are removed.
                clean = Image.new("RGBA", image.size)
                clean.paste(image)
                full_data, dimensions = _encode_webp(clean, 1280, MAX_FULL_BYTES)
                thumb_data, _ = _encode_webp(clean, 480, MAX_THUMB_BYTES)
    except ProductImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ProductImageError("File không phải ảnh hợp lệ hoặc ảnh đã bị hỏng.") from error
    digest = hashlib.sha256(full_data + b"\0" + thumb_data).hexdigest()
    return dict(digest=digest, full_data=full_data, thumb_data=thumb_data,
                full_size=len(full_data), thumb_size=len(thumb_data),
                width=dimensions[0], height=dimensions[1])


def store_product_image(db, prepared):
    """Insert in the caller's transaction; never commit independently of a product."""
    if prepared is None:
        return ""
    if db.get_bind().dialect.name == "postgresql":
        # Serialize quota/dedup decisions across Vercel instances.
        db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": IMAGE_STORE_LOCK})
    digest = prepared["digest"]
    exists = db.execute(select(product_images.c.digest).where(product_images.c.digest == digest)).scalar()
    if not exists:
        used = db.execute(select(func.coalesce(func.sum(
            product_images.c.full_size + product_images.c.thumb_size), 0))).scalar()
        if used + prepared["full_size"] + prepared["thumb_size"] > IMAGE_STORAGE_BUDGET:
            raise ProductImageError("Kho ảnh đã đạt giới hạn 100 MB. Vui lòng xuất bản sao và dọn ảnh cũ trước khi tải thêm.")
        db.execute(product_images.insert().values(**prepared))
    return f"/media/products/{digest}/full.webp"


def _cached_image_bytes(key):
    with _image_response_cache_lock:
        data = _image_response_cache.get(key)
        if data is not None:
            _image_response_cache.move_to_end(key)
        return data


def _remember_image_bytes(key, data):
    global _image_response_cache_bytes
    if len(data) > IMAGE_RESPONSE_CACHE_BYTES or IMAGE_RESPONSE_CACHE_ENTRIES < 1:
        return
    with _image_response_cache_lock:
        previous = _image_response_cache.pop(key, None)
        if previous is not None:
            _image_response_cache_bytes -= len(previous)
        _image_response_cache[key] = data
        _image_response_cache_bytes += len(data)
        while (_image_response_cache_bytes > IMAGE_RESPONSE_CACHE_BYTES
               or len(_image_response_cache) > IMAGE_RESPONSE_CACHE_ENTRIES):
            _, evicted = _image_response_cache.popitem(last=False)
            _image_response_cache_bytes -= len(evicted)


def _clear_image_response_cache():
    """Release cached bytes, including retained engine references."""
    global _image_response_cache_bytes
    with _image_response_cache_lock:
        _image_response_cache.clear()
        _image_response_cache_bytes = 0


def product_image_response(db, digest, variant):
    if not re.fullmatch(r"[a-f0-9]{64}", digest) or variant not in ("full", "thumb"):
        return Response(status=404, headers={"Cache-Control": "no-store"})
    size_column = product_images.c.full_size if variant == "full" else product_images.c.thumb_size
    etag = f"{digest}-{variant}"
    not_modified = request.if_none_match.contains_weak(etag)
    needs_body = request.method != "HEAD" and not not_modified
    # Scope by bind so an image read from one database cannot prove that it
    # exists in another (including isolated test databases).
    cache_key = (db.get_bind(), digest, variant)
    cached_data = _cached_image_bytes(cache_key)
    if cached_data is not None:
        size = len(cached_data)
        body = cached_data if needs_body else b""
    else:
        columns = [size_column]
        if needs_body:
            columns.append(product_images.c.full_data if variant == "full" else product_images.c.thumb_data)
        # One round trip for cold image requests; HEAD/304 never read image bytes.
        row = db.execute(select(*columns).where(product_images.c.digest == digest)).first()
        if row is None:
            return Response(status=404, headers={"Cache-Control": "no-store"})
        size = row[0]
        body = bytes(row[1]) if needs_body else b""
        if needs_body:
            _remember_image_bytes(cache_key, body)
    response = Response(body, status=304 if not_modified else 200, mimetype="image/webp")
    if not not_modified:
        response.content_length = size
    response.set_etag(etag)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers["Vercel-CDN-Cache-Control"] = "public, s-maxage=31536000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
