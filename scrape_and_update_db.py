import os
import sqlite3
import re
import requests
from bs4 import BeautifulSoup

DB_FILE = 'rental_shop.db'
URL = 'https://imginn.com/cheriedresschothuevay/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_name(caption):
    # Trích xuất tên váy (thường nằm trước dòng "Mã:" hoặc "Size:" hoặc dòng chứa "nhà")
    lines = caption.split('\n')
    for line in lines:
        line = line.strip()
        # Bỏ qua các emoji ở đầu dòng nếu có
        line_clean = re.sub(r'^[^\w\s]+', '', line).strip()
        if not line_clean:
            continue
        # Nếu dòng chứa các thông tin đặc trưng của tên thiết kế
        if any(kw in line_clean.lower() for kw in ['nhà', 'của', 'jolie', 'joli', 'sò', 'vintage', 'design', 'loris', 'loft']):
            return line_clean
        # Nếu là dòng đầu tiên có chữ
        if len(line_clean) > 3 and not any(kw in line_clean.lower() for kw in ['mã:', 'size:', 'màu:', 'giá:', 'hotline', 'địa chỉ']):
            return line_clean
    return "Váy Thiết Kế Chérie"

def parse_instagram_data():
    print("[*] Đang tải trang Instagram Chérie Dress qua imginn...")
    response = requests.get(URL, headers=HEADERS, timeout=15)
    if response.status_code != 200:
        print(f"[-] Lỗi tải trang: {response.status_code}")
        return []
        
    soup = BeautifulSoup(response.text, 'html.parser')
    posts = soup.find_all('a', href=re.compile(r'/p/'))
    
    # Nếu không tìm thấy bằng a /p/, thử tìm tất cả các ảnh có class hoặc có alt
    if not posts:
        posts = soup.find_all('div', class_='post')
        
    print(f"[+] Tìm thấy {len(posts)} bài đăng từ trang trung gian.")
    
    dresses = []
    for post in posts:
        img = post.find('img')
        if not img:
            continue
            
        img_url = img.get('data-src') or img.get('src')
        caption = img.get('alt', '')
        
        if not img_url or not caption:
            continue
            
        # 1. Trích xuất tên váy
        name = clean_name(caption)
        
        # 2. Trích xuất Size
        size_match = re.search(r'Size:\s*([SML])', caption, re.IGNORECASE)
        if not size_match:
            continue
        size = size_match.group(1).upper()
        
        # 3. Trích xuất màu sắc
        color_match = re.search(r'Màu:\s*([^\n#|]+)', caption, re.IGNORECASE)
        color = color_match.group(1).strip() if color_match else "Kem"
        
        # 4. Trích xuất giá thuê
        price_match = re.search(r'Giá\s+thuê:\s*(\d+)k', caption, re.IGNORECASE)
        if price_match:
            price = int(price_match.group(1)) * 1000
        else:
            # mặc định 300,000đ nếu không ghi giá
            price = 300000
            
        # 5. Đặt tiền cọc (thường gấp 4-5 lần giá thuê, hoặc cọc mặc định 1.5M)
        deposit = price * 5
        if deposit < 1000000:
            deposit = 1000000
        elif deposit > 3000000:
            deposit = 2500000
            
        # 6. Xác định Phân Nhóm (Category) dựa trên tên hoặc mô tả
        category = "Váy Dạ Hội"
        if any(kw in name.lower() or kw in caption.lower() for kw in ['cưới', 'wedding', 'bridal']):
            category = "Váy Cưới"
        elif any(kw in name.lower() or kw in caption.lower() for kw in ['áo dài', 'ăn hỏi', 'hỷ']):
            category = "Váy Ăn Hỏi"
            
        dresses.append({
            'name': name,
            'category': category,
            'size': size,
            'color': color,
            'price': price,
            'deposit': deposit,
            'image_url': img_url
        })
        
    return dresses

def update_database(dresses):
    if not dresses:
        print("[-] Không có dữ liệu váy để cập nhật.")
        return
        
    if not os.path.exists(DB_FILE):
        print(f"[-] Cơ sở dữ liệu {DB_FILE} chưa tồn tại, vui lòng chạy app.py trước.")
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Xóa sạch bảng dresses cũ
    print("[*] Đang xóa kho váy cũ...")
    cursor.execute("DELETE FROM dresses")
    
    # Thêm váy mới cào được
    print(f"[*] Đang nạp {len(dresses)} váy thực tế từ Instagram vào database...")
    for d in dresses:
        cursor.execute('''
            INSERT INTO dresses (name, category, size, color, price, deposit, image_url, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Sẵn sàng')
        ''', (d['name'], d['category'], d['size'], d['color'], d['price'], d['deposit'], d['image_url']))
        
    conn.commit()
    conn.close()
    print("[+] Cập nhật cơ sở dữ liệu thành công với sản phẩm Instagram thực tế!")

if __name__ == '__main__':
    dresses = parse_instagram_data()
    update_database(dresses)
