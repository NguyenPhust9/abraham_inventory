# Kho Xe Đạp — Web quản lý tồn kho

Ứng dụng web Python (Flask) gồm:
- **Trang khách xem** (`/`): xem danh sách xe, giá, màu, tồn kho — **không cần đăng nhập**.
- **Trang quản lý** (`/admin`): thêm / sửa / xóa sản phẩm, nhập dữ liệu hàng loạt từ file Excel/CSV — **cần đăng nhập**.

## 1. Cài đặt (chạy trên máy của bạn)

Yêu cầu: đã cài Python 3.9+ (tải tại python.org nếu chưa có).

Mở Terminal / Command Prompt, chạy lần lượt:

```bash
cd đường-dẫn-tới-thư-mục-bikeshop
pip install -r requirements.txt
python app.py
```

Sau đó mở trình duyệt vào: **http://127.0.0.1:5000**

## 2. Tài khoản admin mặc định

- Tài khoản: `admin`
- Mật khẩu: `bike123`

**⚠️ Đổi mật khẩu trước khi dùng thật.** Cách đổi — mở file `app.py`, sửa 2 dòng đầu:

```python
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "bike123")
```

Đổi chữ `"admin"` và `"bike123"` thành tài khoản/mật khẩu bạn muốn.

Cách an toàn hơn: thay vì sửa trực tiếp trong code, đặt biến môi trường trước khi chạy:
```bash
export ADMIN_USERNAME="ten-cua-ban"
export ADMIN_PASSWORD="mat-khau-manh-cua-ban"
python app.py
```

## 3. Dữ liệu ban đầu

File `seed_data.json` chứa toàn bộ 387 sản phẩm lấy từ file Excel tồn kho bạn đã gửi.
Lần đầu chạy `python app.py`, hệ thống tự nạp dữ liệu này vào database `shop.db` (SQLite — 1 file, không cần cài thêm phần mềm database nào khác).

Từ lần sau, dữ liệu nằm trong `shop.db` — bạn chỉnh sửa gì trong trang admin sẽ lưu vĩnh viễn ở đó (không bị mất khi tắt server).

## 4. Nhập dữ liệu Excel/CSV mới

Vào `/admin` → mục "Nhập dữ liệu hàng loạt" → chọn file `.xlsx` hoặc `.csv` có các cột:

| Mã hàng hóa | Tên hàng hóa | Loại hàng hóa | Đơn vị tính | Số lượng tồn | SL đã đặt chưa giao |
|---|---|---|---|---|---|

- Mã hàng hóa đã tồn tại → **cập nhật** thông tin.
- Mã hàng hóa mới → **thêm mới** vào hệ thống.
- Giá bán không nằm trong file import — sau khi nhập, vào bảng danh sách sửa giá thủ công (hoặc thêm cột "Giá" và mình có thể chỉnh code để đọc thêm cột đó).

## 5. Đưa lên mạng để khách quét QR dùng thật (deploy)

Chạy `python app.py` chỉ chạy trên máy bạn (localhost) — người khác chưa truy cập được. Để có link công khai, chọn 1 trong các dịch vụ hosting Python miễn phí/giá rẻ, ví dụ:

- **Render.com** (có gói miễn phí, dễ dùng nhất cho người mới)
- **Railway.app**
- **PythonAnywhere**

Các bước chung (lấy ví dụ Render):
1. Đưa toàn bộ thư mục này lên GitHub (tạo repo mới, upload code).
2. Vào Render.com → "New Web Service" → chọn repo GitHub vừa tạo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (cần thêm `gunicorn` vào `requirements.txt`)
5. Vào mục Environment Variables, thêm `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY` (giá trị bạn tự đặt, không dùng giá trị mặc định trong code).
6. Sau khi deploy xong, Render cho bạn 1 link dạng `https://ten-app.onrender.com` — dùng link này để tạo mã QR.

**Lưu ý về dữ liệu khi deploy:** một số hosting miễn phí (như Render free tier) **không giữ file SQLite lâu dài** — mỗi lần server khởi động lại có thể mất dữ liệu. Nếu bạn định dùng lâu dài/dữ liệu quan trọng, nên nâng cấp sang database ngoài như PostgreSQL (Render/Railway đều có gói Postgres miễn phí đi kèm) — báo mình nếu cần, mình sẽ chỉnh code qua Postgres.

## 6. Cấu trúc thư mục

```
bikeshop/
├── app.py               # Toàn bộ logic server: routes, database, đăng nhập
├── seed_data.json        # Dữ liệu tồn kho ban đầu (387 sản phẩm)
├── requirements.txt      # Danh sách thư viện Python cần cài
├── templates/
│   ├── base.html
│   ├── catalog.html       # Trang khách xem
│   ├── login.html         # Trang đăng nhập admin
│   └── dashboard.html     # Trang quản lý (CRUD + import)
└── static/
    ├── style.css
    └── catalog.js          # Tìm kiếm/lọc phía khách hàng
```
