import sqlite3
import os

DB_FILE = 'rental_shop.db'

def init_db():
    # Xóa file cũ nếu có để khởi tạo sạch
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Tạo bảng Dresses
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        size TEXT NOT NULL,
        color TEXT NOT NULL,
        price INTEGER NOT NULL,
        deposit INTEGER NOT NULL,
        image_url TEXT,
        status TEXT NOT NULL DEFAULT 'Sẵn sàng'
    )
    ''')
    
    # 2. Tạo bảng Bookings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dress_id INTEGER NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        total_price INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'Chờ duyệt',
        payment_status TEXT NOT NULL DEFAULT 'Đã cọc',
        FOREIGN KEY (dress_id) REFERENCES dresses (id)
    )
    ''')
    
    # 3. Nạp dữ liệu váy mẫu cho Chérie Dress
    dresses_data = [
        ("Váy Cưới Trễ Vai Satin Trắng (Chérie Signature)", "Váy Cưới", "M", "Trắng", 800000, 3000000, "/static/images/wedding_satin.jpg", "Sẵn sàng"),
        ("Đầm Dạ Hội Kim Sa Đỏ Quyến Rũ", "Váy Dạ Hội", "S", "Đỏ", 350000, 1500000, "/static/images/evening_red.jpg", "Sẵn sàng"),
        ("Đầm Dạ Hội Cúp Ngực Đen Huyền Bí", "Váy Dạ Hội", "M", "Đen", 300000, 1200000, "/static/images/evening_black.jpg", "Sẵn sàng"),
        ("Áo Dài Ăn Hỏi Gấm Đỏ Truyền Thống", "Váy Ăn Hỏi", "L", "Đỏ", 250000, 1000000, "/static/images/aodai_red.jpg", "Sẵn sàng"),
        ("Đầm Công Chúa Xoè Bồng Trắng Tinh Khôi", "Váy Dạ Hội", "S", "Trắng", 400000, 2000000, "/static/images/princess_white.jpg", "Sẵn sàng"),
        ("Váy Dạ Hội Đính Đá Sparkle Pink", "Váy Dạ Hội", "M", "Hồng", 450000, 2000000, "/static/images/evening_pink.jpg", "Sẵn sàng")
    ]
    
    cursor.executemany('''
    INSERT INTO dresses (name, category, size, color, price, deposit, image_url, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', dresses_data)
    
    # 4. Nạp một số lịch đặt mẫu (để trang quản trị có biểu đồ doanh thu và lịch biểu)
    bookings_data = [
        # Đơn 1: Đã hoàn thành (thu 1.6M)
        (1, "Nguyễn Thu Thảo", "0982345678", "2026-07-01", "2026-07-03", 1600000, "Đã trả", "Đã thanh toán hết"),
        # Đơn 2: Đang thuê (thu 700K)
        (2, "Lê Hồng Nhung", "0912345678", "2026-07-07", "2026-07-09", 700000, "Đang thuê", "Đã thanh toán hết"),
        # Đơn 3: Chờ duyệt (sắp thuê)
        (3, "Trần Hải Yến", "0909876543", "2026-07-12", "2026-07-14", 600000, "Chờ duyệt", "Đã cọc"),
        # Đơn 4: Đã thanh toán trước cho cuối tháng
        (5, "Phạm Minh Thư", "0966778899", "2026-07-25", "2026-07-26", 400000, "Chờ duyệt", "Đã thanh toán hết")
    ]
    
    cursor.executemany('''
    INSERT INTO bookings (dress_id, customer_name, customer_phone, start_date, end_date, total_price, status, payment_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', bookings_data)
    
    conn.commit()
    conn.close()
    print("[+] Khởi tạo thành công cơ sở dữ liệu SQLite: rental_shop.db")

if __name__ == '__main__':
    init_db()
