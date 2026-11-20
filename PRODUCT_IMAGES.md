# Ảnh sản phẩm

Ảnh mới được lưu trong bảng `product_images` của PostgreSQL hiện có. Đây là bảng dữ liệu của ứng dụng, không phải dịch vụ Supabase Storage. Không còn cần Cloudinary để tải lên hoặc hiển thị ảnh mới; không cần đăng ký dịch vụ mới.

Trong trang quản trị, tìm sản phẩm → **Sửa** → chọn JPG, PNG hoặc WebP → **Lưu riêng ảnh**. Thao tác này chỉ đổi ảnh, giữ nguyên tồn kho và giá. Nút lưu thay đổi thông thường vẫn lưu toàn bộ biểu mẫu.

- File đầu vào tối đa 4 MiB và 24 megapixel; chỉ nhận ảnh tĩnh.
- Tự xoay theo EXIF, bỏ metadata, nén WebP: bản đầy đủ tối đa 1280 px / 200 KiB; ảnh thu nhỏ tối đa 480 px / 50 KiB.
- Nội dung trùng chỉ lưu một lần. URL chứa hash và được cache dài hạn; đổi ảnh tạo URL mới.
- Ngân sách ảnh là 100 MiB, tính cả ảnh đã gỡ khỏi sản phẩm. Không tự xóa ảnh cũ vì nhiều sản phẩm có thể dùng chung. Khi hết ngân sách, upload bị từ chối và giữ nguyên dữ liệu cũ.
- Dữ liệu ảnh vẫn sử dụng dung lượng/băng thông của database và Vercel. Giới hạn trên không phải cam kết miễn phí vô hạn.

## Ảnh cũ

Các tham chiếu Cloudinary cũ được giữ nguyên trong `products.image_filename`, nhưng không gửi cho trình duyệt khi cloud bị khóa. Các sản phẩm trước đây có ảnh vẫn có mặt trong danh mục với nhãn “Chưa có ảnh”. Upload ảnh thay thế sẽ cập nhật tham chiếu của sản phẩm đó; bản sao trước triển khai giữ đường dẫn cũ.

Ngày 20/11/2026, các URL mẫu của cloud `desf1gsdl` trả HTTP 401 / cloud disabled. Chưa khôi phục được ảnh sản phẩm cũ. Hai file ảnh tìm được trong lịch sử Git là ảnh quầy bán đồ ăn, không phải ảnh sản phẩm, nên không dùng chúng để thay thế. Có thể khôi phục từ thư mục ảnh gốc hoặc từ Cloudinary sau khi tài khoản được mở lại. Không đoán ghép ảnh theo tên hoặc dùng ảnh minh họa làm ảnh sản phẩm.

## Khởi tạo và sao lưu

Môi trường Vercel phải chạy migration một lần trước khi triển khai. Công cụ đọc cùng cấu hình `.env.pooler`, `.env.local`, `.env` như ứng dụng; không đưa các file bí mật lên Git.

```powershell
.\venv\Scripts\python.exe manage_product_images.py --init
.\venv\Scripts\python.exe manage_product_images.py --backup ..\outputs\image-backup-YYYYMMDD
```

Thư mục backup phải là đường dẫn mới. Công cụ chỉ đọc DB khi backup, xuất `manifest.json` chứa mã sản phẩm/đường dẫn ảnh và các file `full.webp`, `thumb.webp` theo hash. Kiểm tra checksum từng ảnh trước khi hoàn tất. Nên sao lưu sau các đợt thêm ảnh và giữ một bản trên máy/thư mục lưu trữ riêng. Khi cần phục hồi, đối chiếu mã sản phẩm trong manifest và tải `full.webp` qua trang quản trị. Công cụ không xóa dữ liệu.

Ảnh mất từ Cloudinary chỉ có đường dẫn trong manifest, không có bytes ảnh để phục hồi. Bản backup không thể tự tạo lại nội dung đã bị nhà cung cấp chặn.

## Kiểm tra

```powershell
.\venv\Scripts\python.exe -B -m unittest test_product_images test_inventory_chat
node --check static/catalog.js
node --check static/product-images.js
```

Các test dùng SQLite trong bộ nhớ, không truy cập cơ sở dữ liệu thật. Bao gồm phân quyền upload, nén/giới hạn ảnh, chống trùng, rollback, tham chiếu dùng chung, danh mục khi ảnh mất và phản hồi GET/HEAD/304/404.
