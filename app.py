import os
import re
import cloudinary  # type: ignore
import cloudinary.uploader  # type: ignore
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash  # type: ignore
from flask_login import (  # type: ignore
    LoginManager, UserMixin, login_user, logout_user,
    login_required
)
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text, func  # type: ignore
from sqlalchemy.orm import sessionmaker, declarative_base  # type: ignore
import pandas as pd  # type: ignore
from werkzeug.utils import secure_filename  # type: ignore


# ---------- Config ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shop.db")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "bike123")
SECRET_KEY = os.environ.get("SECRET_KEY", "doi-chuoi-bi-mat-nay-truoc-khi-deploy")
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)
app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY


# ---------- Database ----------
Base = declarative_base()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
    )
else:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False}
    )
SessionLocal = sessionmaker(bind=engine)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    model = Column(String, nullable=False)
    color = Column(String, default="")
    category = Column(String, default="")
    unit = Column(String, default="Chiếc")
    stock = Column(Integer, default=0)
    reserved = Column(Integer, default=0)
    price = Column(Float, nullable=True)
    image_filename = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def available(self):
        stock = self.stock or 0
        reserved = self.reserved or 0
        return max(stock - reserved, 0)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "model": self.model,
            "color": self.color,
            "category": self.category,
            "unit": self.unit,
            "stock": self.stock or 0,
            "reserved": self.reserved or 0,
            "available": self.available,
            "price": self.price,
            "image": self.image_filename,
        }


Base.metadata.create_all(engine)


# ---------- Upload folder ----------
IMAGE_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)


def ensure_columns():
    """
    Đảm bảo database cũ vẫn chạy được nếu trước đây thiếu cột.
    """
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA table_info(products)")).fetchall()
        cols = [r[1] for r in res]

        if "image_filename" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN image_filename VARCHAR"))

        if "unit" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN unit VARCHAR DEFAULT 'Chiếc'"))

        if "price" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN price FLOAT"))

        conn.commit()


if engine.dialect.name == "sqlite":
    try:
        ensure_columns()
    except Exception:
        pass


# ---------- Auth ----------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin_login"


class AdminUser(UserMixin):
    id = "admin"


@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return AdminUser()
    return None


# ---------- Helpers ----------
def normalize_model_name(model_name: str):
    """
    Gộp các mẫu xe có phần ghi chú trong ngoặc về cùng một tên mẫu.

    Ví dụ:
    24BIKE Nhôm (tem đậm) -> 24BIKE Nhôm
    24BIKE Nhôm (tem lợt) -> 24BIKE Nhôm
    24BIKE Nhôm (tem xám) -> 24BIKE Nhôm
    """
    if not model_name:
        return ""

    name = str(model_name).strip()

    # Xóa phần ghi chú cuối cùng nằm trong ngoặc
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)

    # Xóa khoảng trắng dư
    name = re.sub(r"\s+", " ", name).strip()

    return name


def split_model_color(name: str):
    """
    Tách dữ liệu nhập từ file dạng:
    'Tên xe - Màu' -> model, color

    Sau khi tách màu, model cũng được chuẩn hóa để tránh tách card ngoài trang khách.
    """
    if not name:
        return "", ""

    name = str(name).strip()
    parts = name.rsplit("-", 1)

    if len(parts) == 2 and parts[1].strip():
        model = normalize_model_name(parts[0].strip())
        color = parts[1].strip()
        return model, color

    return normalize_model_name(name), ""


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def save_product_image(file, product_id):
    if not file or not file.filename:
        return ""

    try:
        result = cloudinary.uploader.upload(
            file,
            folder="abraham_inventory/products",
            public_id=f"product_{product_id}",
            overwrite=True,
            resource_type="image",
        )
        return result.get("secure_url", "")
    except Exception as e:
        print(f"Loi upload Cloudinary: {e}")
        return ""


def seed_if_empty():
    db = SessionLocal()
    try:
        if db.query(Product).count() == 0:
            seed_path = os.path.join(BASE_DIR, "seed_data.json")
            if os.path.exists(seed_path):
                import json

                with open(seed_path, encoding="utf-8") as f:
                    rows = json.load(f)

                for r in rows:
                    db.add(Product(
                        code=r["code"],
                        model=normalize_model_name(r["model"]),
                        color=r.get("color", ""),
                        category=r.get("category", ""),
                        unit=r.get("unit", "Chiếc") or "Chiếc",
                        stock=safe_int(r.get("stock")),
                        reserved=safe_int(r.get("reserved")),
                        price=safe_float(r.get("price")),
                    ))

                db.commit()
    finally:
        db.close()


# ---------- Public routes ----------
@app.route("/")
def catalog():
    return render_template("catalog.html")


@app.route("/api/products")
def api_products():
    """
    API cho trang khách.

    Điểm quan trọng:
    - Admin vẫn quản lý từng mã hàng riêng.
    - API trả model đã chuẩn hóa để frontend tự gộp chung card.
    - original_model giữ lại tên gốc nếu sau này cần xem/debug.
    """
    db = SessionLocal()
    try:
        products = db.query(Product).order_by(Product.model, Product.color).all()

        out = []

        for p in products:
            d = p.to_dict()

            d["original_model"] = p.model
            d["model"] = normalize_model_name(p.model)

            d["image_url"] = p.image_filename if p.image_filename else None

            out.append(d)

        return jsonify(out)

    finally:
        db.close()


# ---------- Admin auth ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            login_user(AdminUser())
            return redirect(url_for("admin_dashboard"))

        flash("Sai tài khoản hoặc mật khẩu.")

    return render_template("login.html")


@app.route("/admin/logout")
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for("catalog"))


# ---------- Admin dashboard ----------
@app.route("/admin")
@login_required
def admin_dashboard():
    page = request.args.get("page", "1")

    try:
        page = max(1, int(page))
    except ValueError:
        page = 1

    per_page = 10

    db = SessionLocal()
    try:
        total_products = db.query(Product).count()

        products = (
            db.query(Product)
            .order_by(Product.model, Product.color, Product.code)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        all_products = db.query(Product).all()

        categories = sorted({
            p.category for p in all_products
            if p.category and str(p.category).strip()
        })

        total_stock = db.query(Product).with_entities(func.sum(Product.stock)).scalar() or 0
        total_available = sum([p.available for p in all_products])

        total_pages = max(1, (total_products + per_page - 1) // per_page)

        return render_template(
            "dashboard.html",
            products=products,
            categories=categories,
            page=page,
            total_pages=total_pages,
            total_products=total_products,
            total_stock=total_stock,
            total_available=total_available,
            per_page=per_page,
        )

    finally:
        db.close()


@app.route("/admin/products/add", methods=["POST"])
@login_required
def admin_add_product():
    db = SessionLocal()
    try:
        code = request.form.get("code", "").strip()

        if not code:
            flash("Vui lòng nhập mã hàng.")
            return redirect(url_for("admin_dashboard"))

        if db.query(Product).filter_by(code=code).first():
            flash(f"Mã hàng '{code}' đã tồn tại.")
            return redirect(url_for("admin_dashboard"))

        model = request.form.get("model", "").strip()

        if not model:
            flash("Vui lòng nhập tên mẫu xe.")
            return redirect(url_for("admin_dashboard"))

        price = request.form.get("price", "").strip()

        p = Product(
            code=code,
            model=normalize_model_name(model),
            color=request.form.get("color", "").strip(),
            category=request.form.get("category", "").strip(),
            unit=request.form.get("unit", "Chiếc").strip() or "Chiếc",
            stock=safe_int(request.form.get("stock")),
            reserved=safe_int(request.form.get("reserved")),
            price=safe_float(price),
        )

        db.add(p)
        db.commit()

        file = request.files.get("image")
        image_name = save_product_image(file, p.id)

        if image_name:
            p.image_filename = image_name
            db.commit()

        flash("Đã thêm sản phẩm.")

    finally:
        db.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/products/<int:product_id>/edit", methods=["POST"])
@login_required
def admin_edit_product(product_id):
    db = SessionLocal()
    try:
        p = db.query(Product).get(product_id)

        if not p:
            flash("Không tìm thấy sản phẩm.")
            return redirect(url_for("admin_dashboard"))

        new_code = request.form.get("code", p.code).strip()

        if not new_code:
            flash("Mã hàng không được để trống.")
            return redirect(url_for("admin_dashboard"))

        duplicate = (
            db.query(Product)
            .filter(Product.code == new_code, Product.id != product_id)
            .first()
        )

        if duplicate:
            flash(f"Mã hàng '{new_code}' đã tồn tại ở sản phẩm khác.")
            return redirect(url_for("admin_dashboard"))

        model = request.form.get("model", "").strip()

        if not model:
            flash("Tên mẫu xe không được để trống.")
            return redirect(url_for("admin_dashboard"))

        p.code = new_code
        p.model = normalize_model_name(model)
        p.color = request.form.get("color", "").strip()
        p.category = request.form.get("category", "").strip()
        p.unit = request.form.get("unit", "Chiếc").strip() or "Chiếc"
        p.stock = safe_int(request.form.get("stock"))
        p.reserved = safe_int(request.form.get("reserved"))
        p.price = safe_float(request.form.get("price", "").strip())

        file = request.files.get("image")
        image_name = save_product_image(file, p.id)

        if image_name:
            p.image_filename = image_name

        db.commit()

        flash("Đã cập nhật sản phẩm.")

    finally:
        db.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/products/<int:product_id>/delete-image", methods=["POST"])
@login_required
def admin_delete_product_image(product_id):
    db = SessionLocal()
    try:
        p = db.query(Product).get(product_id)

        if not p:
            flash("Không tìm thấy sản phẩm.")
            return redirect(url_for("admin_dashboard"))

        if p.image_filename:
            try:
                public_id = f"abraham_inventory/products/product_{p.id}"
                cloudinary.uploader.destroy(public_id, resource_type="image")
            except Exception as e:
                print(f"Loi xoa anh Cloudinary: {e}")

            p.image_filename = ""
            db.commit()
            flash("Đã xóa ảnh sản phẩm.")
        else:
            flash("Sản phẩm này chưa có ảnh.")

    finally:
        db.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@login_required
def admin_delete_product(product_id):
    db = SessionLocal()
    try:
        p = db.query(Product).get(product_id)

        if p:
            db.delete(p)
            db.commit()
            flash("Đã xóa sản phẩm.")

    finally:
        db.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/import", methods=["POST"])
@login_required
def admin_import():
    file = request.files.get("file")

    if not file or file.filename == "":
        flash("Chưa chọn file để nhập.")
        return redirect(url_for("admin_dashboard"))

    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        flash(f"Không đọc được file: {e}")
        return redirect(url_for("admin_dashboard"))

    if "Mã hàng hóa" not in df.columns:
        flash("File thiếu cột bắt buộc: Mã hàng hóa.")
        return redirect(url_for("admin_dashboard"))

    has_name = "Tên hàng hóa" in df.columns
    has_category = "Loại hàng hóa" in df.columns
    unit_col = "Đơn vị tính" if "Đơn vị tính" in df.columns else (
        "Đơn vị tính chính" if "Đơn vị tính chính" in df.columns else None
    )
    has_stock = "Số lượng tồn" in df.columns
    has_reserved = "SL đã đặt chưa giao" in df.columns
    has_price = "Đơn giá bán" in df.columns

    df = df.fillna(0)

    db = SessionLocal()
    added, updated, skipped = 0, 0, 0

    BATCH_SIZE = 1000

    try:
        # Lay toan bo (id, code) hien co 1 lan duy nhat, khong load ca
        # object de tiet kiem bo nho va thoi gian query.
        existing_by_code = {
            code: pid for pid, code in db.query(Product.id, Product.code).all()
        }

        to_insert = []
        to_update = []

        for row in df.itertuples(index=False):
            row = dict(zip(df.columns, row))

            code = str(row["Mã hàng hóa"]).strip()

            if not code or code == "0":
                continue

            existing_id = existing_by_code.get(code)

            if existing_id:
                # San pham da co: chi cap nhat cot nao co trong file,
                # cot khong co trong file thi giu nguyen du lieu cu.
                data = {"id": existing_id}

                if has_name:
                    name = str(row["Tên hàng hóa"]).strip()
                    if name and name != "0":
                        model, color = split_model_color(name)
                        data["model"] = model
                        data["color"] = color

                if has_category:
                    category = str(row.get("Loại hàng hóa", "")).strip()
                    if category and category != "0":
                        data["category"] = category

                if unit_col:
                    unit = str(row.get(unit_col, "")).strip()
                    if unit and unit != "0":
                        data["unit"] = unit

                if has_stock:
                    data["stock"] = safe_int(row.get("Số lượng tồn", 0))

                if has_reserved:
                    data["reserved"] = safe_int(row.get("SL đã đặt chưa giao", 0))

                if has_price:
                    price_value = safe_float(row.get("Đơn giá bán"))
                    if price_value is not None:
                        data["price"] = price_value

                to_update.append(data)
                updated += 1

            else:
                # San pham chua co: bat buoc phai co ten de tao moi.
                if not has_name:
                    skipped += 1
                    continue

                name = str(row["Tên hàng hóa"]).strip()

                if not name or name == "0":
                    skipped += 1
                    continue

                model, color = split_model_color(name)

                to_insert.append({
                    "code": code,
                    "model": model,
                    "color": color,
                    "category": str(row.get("Loại hàng hóa", "")).strip() if has_category else "",
                    "unit": (str(row.get(unit_col, "Chiếc")).strip() or "Chiếc") if unit_col else "Chiếc",
                    "stock": safe_int(row.get("Số lượng tồn", 0)) if has_stock else 0,
                    "reserved": safe_int(row.get("SL đã đặt chưa giao", 0)) if has_reserved else 0,
                    "price": safe_float(row.get("Đơn giá bán")) if has_price else None,
                })
                added += 1

            # Flush theo batch de tranh giu transaction qua lon trong bo nho.
            if len(to_insert) >= BATCH_SIZE:
                db.bulk_insert_mappings(Product, to_insert)
                db.commit()
                to_insert.clear()

            if len(to_update) >= BATCH_SIZE:
                db.bulk_update_mappings(Product, to_update)
                db.commit()
                to_update.clear()

        # Flush phan con lai.
        if to_insert:
            db.bulk_insert_mappings(Product, to_insert)
            db.commit()

        if to_update:
            db.bulk_update_mappings(Product, to_update)
            db.commit()

        message = f"Nhập xong: thêm mới {added}, cập nhật {updated}."
        if skipped:
            message += f" Bỏ qua {skipped} dòng thiếu tên hàng."
        flash(message)

    except Exception as e:
        db.rollback()
        flash(f"Lỗi khi nhập dữ liệu: {e}")

    finally:
        db.close()

    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    seed_if_empty()
    app.run(host="0.0.0.0", port=5000, debug=True)