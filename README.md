# Outdated Website Finder 🕵️‍♂️

Công cụ tự động quét, phát hiện và chấm điểm mức độ lỗi thời của các website trên Internet. Hỗ trợ đắc lực cho mô hình **Website Flipping (Mua đi bán lại website)** bằng cách tìm kiếm các website cũ nhưng còn hoạt động và có tiềm năng nâng cấp giao diện (redesign) để bán lại hoặc khai thác.

---

## 🛠 Hướng dẫn Cài đặt

1. Đảm bảo hệ thống đã cài đặt Python 3.
2. Cài đặt các thư viện cần thiết bằng cách chạy lệnh sau tại thư mục này:
   ```bash
   pip3 install -r requirements.txt --break-system-packages
   ```

---

## 🚀 Hướng dẫn Sử dụng

### 1. Quét thông qua công cụ tìm kiếm (Dùng Google Dorking qua DuckDuckGo)
Tìm kiếm các website theo một từ khóa / cú pháp cụ thể:
```bash
./finder.py -q 'site:.vn "© 2012" du lich' -l 15
```
*   `-q` hoặc `--query`: Từ khóa tìm kiếm.
*   `-l` hoặc `--limit`: Số lượng kết quả tối đa muốn phân tích (mặc định là 20).

### 2. Quét từ danh sách tên miền có sẵn (Nhập từ file)
Nếu bạn tải danh sách các tên miền cũ/đang đấu giá từ các nguồn khác (ví dụ: `ExpiredDomains.net`), lưu vào một file text (mỗi dòng một tên miền) và chạy lệnh:
```bash
./finder.py -f domains.txt -o my_results.csv
```
*   `-f` hoặc `--file`: Đường dẫn tới file chứa danh sách tên miền.
*   `-o` hoặc `--output`: Tên file CSV kết quả đầu ra (mặc định: `potential_sites.csv`).

### 3. Điều chỉnh tốc độ quét (Delay)
Để tránh bị các trang web chặn hoặc ghi nhận là tấn công DDOS, bạn có thể điều chỉnh thời gian chờ giữa mỗi lượt quét (mặc định là 2.0 giây):
```bash
./finder.py -q '"© 2010" cafe' -d 3.0
```

---

## 💡 Gợi ý Cú pháp Google Dorks Tìm kiếm Hiệu quả

Bạn có thể thay thế cụm từ trong `[...]` bằng lĩnh vực/ngách bạn quan tâm (ví dụ: *lam vuon, cafe, bat dong san, du lich, tin tuc*):

1.  **Tìm theo năm bản quyền cũ**:
    *   `site:.vn "© 2008..2015" [từ khóa]`
    *   `site:.vn "Copyright 2010" [từ khóa]`
2.  **Tìm hệ quản trị nội dung (CMS) phiên bản cũ**:
    *   `site:.vn "Powered by WordPress 3." [từ khóa]` (WordPress phiên bản 3 ra mắt từ năm 2010 - 2013)
    *   `site:.vn "Powered by Joomla 1.5" [từ khóa]`
3.  **Tìm các cấu trúc web cổ**:
    *   `site:.vn intext:"All rights reserved 2011" [từ khóa]`

---

## 📊 Tiêu chí Chấm điểm Lỗi thời (Score)

Mỗi website sau khi quét sẽ được chấm điểm từ **0 đến 100** điểm tiềm năng redesign (điểm càng cao càng đáng đầu tư):

*   **Không hỗ trợ di động (Responsive):** +40 điểm (Website không responsive cực kỳ khó dùng trên điện thoại hiện nay, là cơ hội tốt nhất để redesign).
*   **Dùng bố cục bảng (Table Layout):** +20 điểm (Kiểu thiết kế từ những năm 2000).
*   **Có chứng chỉ SSL (HTTPS):** Nếu không có SSL sẽ được +10 điểm.
*   **Sử dụng thư viện cổ (jQuery 1.x/2.x):** +15 điểm.
*   **Năm bản quyền (Copyright) quá cũ:** Lên tới +25 điểm (Phản ánh việc website đã bị bỏ hoang hoặc không cập nhật nội dung từ lâu).
*   **Có các thẻ HTML đã bị đào thải (center, font, marquee, frame...):** +10 điểm mỗi thẻ.
