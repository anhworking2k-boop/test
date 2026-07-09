#!/usr/bin/env python3
import os
import csv
import re
import time
from urllib.parse import urlparse, quote_plus
import requests
from bs4 import BeautifulSoup
import urllib3
from flask import Flask, render_template, jsonify, request, Response, redirect
from werkzeug.utils import secure_filename

# Import các hàm phân tích lead từ lead_analyzer
from lead_analyzer import analyze_csv_leads, is_vietnamese_lead

app = Flask(__name__, template_folder='templates')
app.config['UPLOAD_FOLDER'] = 'uploads'

# Tạo thư mục uploads nếu chưa có
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Vô hiệu hóa cảnh báo SSL không an toàn
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

CSV_FILE = 'real_scan_results.csv'
FALLBACK_CSV_FILE = 'potential_sites.csv'
LEADS_CSV_FILE = 'local_leads_report.csv'
FIELDNAMES = ['domain', 'url', 'title', 'status', 'ssl', 'responsive', 'table_layout', 'obsolete_tags', 'jquery_version', 'copyright_years', 'score', 'notes']

def search_duckduckgo(query, limit=15):
    """
    Tìm kiếm trên DuckDuckGo Lite
    """
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        if response.status_code == 202 or 'anomaly' in response.text:
            raise Exception("DuckDuckGo yêu cầu xác minh Bot (Captcha). Vui lòng nhập trực tiếp danh sách tên miền.")
        if response.status_code != 200:
            raise Exception(f"Lỗi kết nối tới công cụ tìm kiếm (Status: {response.status_code})")
            
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        
        for a in soup.find_all('a', class_='result__url'):
            href = a.get('href')
            if href:
                if 'duckduckgo.com/l/?kh=' in href:
                    match = re.search(r'uddg=([^&]+)', href)
                    if match:
                        from urllib.parse import unquote
                        href = unquote(match.group(1))
                
                if href.startswith('http') and 'duckduckgo.com' not in href:
                    links.append(href)
                    if len(links) >= limit:
                        break
        return links
    except Exception as e:
        raise e

def clean_url(url):
    """Làm sạch và định dạng URL"""
    if not url:
        return ''
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return f"http://{url}"
    return url

def analyze_website(url):
    """
    Phân tích chi tiết một trang web để phát hiện các yếu tố lỗi thời
    """
    url = clean_url(url)
    result = {
        'url': url,
        'domain': urlparse(url).netloc.replace('www.', ''),
        'status': 'Error',
        'title': 'N/A',
        'ssl': 'No',
        'responsive': 'No',
        'table_layout': 'No',
        'obsolete_tags': 'None',
        'jquery_version': 'N/A',
        'copyright_years': 'N/A',
        'score': 0,
        'notes': ''
    }
    
    if url.startswith('https://'):
        result['ssl'] = 'Yes'
        
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        result['status'] = f"{response.status_code}"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        if soup.title and soup.title.string:
            result['title'] = soup.title.string.strip()
            
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport and 'width=device-width' in str(viewport.get('content', '')):
            result['responsive'] = 'Yes'
        else:
            result['responsive'] = 'No'
            result['score'] += 40
            result['notes'] += "Không Responsive; "

        tables = soup.find_all('table')
        if len(tables) > 4:
            nested_tables = False
            for t in tables:
                if t.find('table'):
                    nested_tables = True
                    break
            if nested_tables:
                result['table_layout'] = 'Yes'
                result['score'] += 20
                result['notes'] += "Table Layout; "

        obsolete_found = []
        for tag in ['font', 'center', 'frame', 'frameset', 'marquee', 'blink', 'nobr']:
            if soup.find(tag):
                obsolete_found.append(tag)
        if obsolete_found:
            result['obsolete_tags'] = ', '.join(obsolete_found)
            result['score'] += 10 * len(obsolete_found)
            result['notes'] += f"Thẻ cổ: {result['obsolete_tags']}; "

        jquery_ver = 'N/A'
        for script in soup.find_all('script', src=True):
            src = script['src'].lower()
            match = re.search(r'jquery[.-]([0-9.]+)', src)
            if match:
                jquery_ver = match.group(1)
                result['jquery_version'] = jquery_ver
                if jquery_ver.startswith(('1.', '2.')):
                    result['score'] += 15
                    result['notes'] += f"jQuery cũ ({jquery_ver}); "
                break

        html_text = response.text
        copyright_pattern = re.compile(r'(?:copyright|©|\(c\))\s*(?:19\d{2}|20\d{2})\s*(?:-\s*(?:19\d{2}|20\d{2}))?', re.IGNORECASE)
        matches = copyright_pattern.findall(html_text)
        
        if not matches:
            footer_text = ""
            for footer_tag in ['footer', 'div']:
                tag_elm = soup.find(footer_tag, class_=re.compile(r'foot|copy', re.I)) or soup.find(footer_tag, id=re.compile(r'foot|copy', re.I))
                if tag_elm:
                    footer_text += tag_elm.get_text()
            year_matches = re.findall(r'\b(20[0-2]\d|19\d{2})\b', footer_text)
            if year_matches:
                matches = year_matches

        if matches:
            years = []
            for m in matches:
                found_years = re.findall(r'\b(20[0-2]\d|19\d{2})\b', m)
                years.extend([int(y) for y in found_years])
            if years:
                latest_year = max(years)
                result['copyright_years'] = str(latest_year)
                current_year = time.localtime().tm_year
                diff = current_year - latest_year
                if diff > 5:
                    result['score'] += min(diff * 5, 25)
                    result['notes'] += f"Bản quyền cũ ({latest_year}); "
        
        if result['ssl'] == 'No':
            result['score'] += 10
            result['notes'] += "Không SSL; "
            
    except requests.exceptions.Timeout:
        result['status'] = 'Timeout'
        result['notes'] = 'Timeout kết nối'
    except requests.exceptions.SSLError:
        result['status'] = 'SSL Error'
        result['notes'] = 'Lỗi SSL'
    except Exception as e:
        result['status'] = 'Failed'
        result['notes'] = f"Lỗi: {str(e)}"
        
    return result

def load_results():
    """
    Đọc dữ liệu từ file CSV chính hoặc file fallback
    """
    results = {}
    active_file = CSV_FILE if os.path.exists(CSV_FILE) else (FALLBACK_CSV_FILE if os.path.exists(FALLBACK_CSV_FILE) else None)
    
    if active_file:
        try:
            with open(active_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        row['score'] = int(row['score'])
                    except:
                        row['score'] = 0
                    domain = row['domain']
                    results[domain] = row
        except Exception as e:
            print(f"[!] Lỗi khi đọc file CSV: {e}")
            
    return results

def save_results(results_dict):
    """
    Ghi dữ liệu vào CSV
    """
    try:
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
            writer.writeheader()
            for r in results_dict.values():
                filtered_r = {k: r.get(k, 'N/A') for k in FIELDNAMES}
                writer.writerow(filtered_r)
        return True
    except Exception as e:
        print(f"[!] Lỗi khi ghi file CSV: {e}")
        return False

# --- FLASK ENDPOINTS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/results', methods=['GET'])
def get_results():
    data = load_results()
    # Chuyển thành list và sắp xếp theo điểm số giảm dần
    sorted_list = sorted(list(data.values()), key=lambda x: x['score'], reverse=True)
    return jsonify(sorted_list)

@app.route('/api/results/<domain>', methods=['DELETE'])
def delete_result(domain):
    data = load_results()
    if domain in data:
        del data[domain]
        save_results(data)
        return jsonify({'success': True, 'message': f"Đã xóa {domain}"})
    return jsonify({'success': False, 'message': f"Không tìm thấy tên miền {domain}"}), 404

@app.route('/api/scan', methods=['POST'])
def run_scan():
    req_data = request.json or {}
    scan_type = req_data.get('type')
    query_str = req_data.get('query', '').strip()
    domains_list = req_data.get('domains', [])
    
    urls_to_scan = []
    
    if scan_type == 'query':
        if not query_str:
            return jsonify({'success': False, 'message': 'Từ khóa tìm kiếm trống.'}), 400
        try:
            links = search_duckduckgo(query_str)
            urls_to_scan.extend(links)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
            
    elif scan_type == 'domains':
        if not domains_list:
            return jsonify({'success': False, 'message': 'Danh sách tên miền trống.'}), 400
        for d in domains_list:
            d = d.strip()
            if d:
                urls_to_scan.append(d)
                
    if not urls_to_scan:
        return jsonify({'success': False, 'message': 'Không tìm thấy website nào để quét.'}), 200

    current_data = load_results()
    new_scanned_results = []
    
    for url in urls_to_scan:
        # Lọc chỉ lấy web Việt Nam
        domain_name = urlparse(clean_url(url)).netloc.replace('www.', '')
        if not is_vietnamese_lead(domain_name, '', url, ''):
            continue
            
        res = analyze_website(url)
        # Chỉ lưu các site sống (status 200) như yêu cầu của user
        if res['status'] == '200':
            domain = res['domain']
            current_data[domain] = res
            new_scanned_results.append(res)
        
    save_results(current_data)
    
    return jsonify({
        'success': True,
        'message': f"Đã quét thành công {len(new_scanned_results)} website Việt Nam đang hoạt động.",
        'scanned': new_scanned_results,
        'all': sorted(list(current_data.values()), key=lambda x: x['score'], reverse=True)
    })

# --- LOCAL LEADS API (GOOGLE MAPS) ---

@app.route('/api/leads', methods=['GET'])
def get_leads():
    """Lấy danh sách khách hàng tiềm năng từ Google Maps đã lưu"""
    leads = []
    if os.path.exists(LEADS_CSV_FILE):
        try:
            with open(LEADS_CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        row['score'] = int(row['score'])
                    except:
                        row['score'] = 0
                    leads.append(row)
        except Exception as e:
            print(f"[!] Lỗi khi đọc file Leads CSV: {e}")
            
    # Trả về danh sách sắp xếp theo độ tiềm năng (score) giảm dần
    return jsonify(sorted(leads, key=lambda x: x['score'], reverse=True))

@app.route('/api/leads/upload', methods=['POST'])
def upload_leads():
    """Tải lên và phân tích file CSV từ Google Maps"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không tìm thấy file tải lên.'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Tên file trống.'}), 400
        
    if file and file.filename.endswith('.csv'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Chạy phân tích file CSV
        print(f"[*] Bắt đầu phân tích file Google Maps: {filepath}...")
        leads = analyze_csv_leads(filepath)
        
        # Xóa file tạm sau khi quét xong
        try:
            os.remove(filepath)
        except:
            pass
            
        return jsonify({
            'success': True,
            'message': f"Phân tích thành công {len(leads)} khách hàng tiềm năng Việt Nam từ Google Maps.",
            'leads': sorted(leads, key=lambda x: x['score'], reverse=True)
        })
        
    return jsonify({'success': False, 'message': 'Định dạng file không được hỗ trợ (chỉ nhận .csv).'}), 400

@app.route('/api/leads/<name>', methods=['DELETE'])
def delete_lead(name):
    """Xóa một lead khỏi danh sách báo cáo"""
    leads = []
    found = False
    if os.path.exists(LEADS_CSV_FILE):
        try:
            with open(LEADS_CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row['name'] == name:
                        found = True
                    else:
                        leads.append(row)
                        
            if found:
                with open(LEADS_CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(leads)
                return jsonify({'success': True, 'message': f"Đã xóa {name}"})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
            
        return jsonify({'success': False, 'message': 'Không tìm thấy lead.'}), 404

# ==========================================
# MVP BỘ ĐẶT LỊCH VÀ QUẢN LÝ CHO THUÊ VÁY
# ==========================================
import sqlite3

RENTAL_DB = 'rental_shop.db'

def init_db_if_not_exists():
    if not os.path.exists(RENTAL_DB):
        conn = sqlite3.connect(RENTAL_DB)
        cursor = conn.cursor()
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
        
        # Seed dữ liệu váy cưới mẫu cho Chérie Dress
        dresses_data = [
            ("Váy Cưới Trễ Vai Satin Trắng (Chérie Signature)", "Váy Cưới", "M", "Trắng", 800000, 3000000, "https://images.unsplash.com/photo-1594552072238-b8a33785b261?auto=format&fit=crop&q=80&w=600", "Sẵn sàng"),
            ("Đầm Dạ Hội Kim Sa Đỏ Quyến Rũ", "Váy Dạ Hội", "S", "Đỏ", 350000, 1500000, "https://images.unsplash.com/photo-1566174053879-31528523f8ae?auto=format&fit=crop&q=80&w=600", "Sẵn sàng"),
            ("Đầm Dạ Hội Cúp Ngực Đen Huyền Bí", "Váy Dạ Hội", "M", "Đen", 300000, 1200000, "https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&q=80&w=600", "Sẵn sàng"),
            ("Áo Dài Ăn Hỏi Gấm Đỏ Truyền Thống", "Váy Ăn Hỏi", "L", "Đỏ", 250000, 1000000, "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?auto=format&fit=crop&q=80&w=600", "Sẵn sàng"),
            ("Đầm Công Chúa Xoè Bồng Trắng Tinh Khôi", "Váy Dạ Hội", "S", "Trắng", 400000, 2000000, "https://images.unsplash.com/photo-1518049362265-d5b2a6467637?auto=format&fit=crop&q=80&w=600", "Sẵn sàng"),
            ("Váy Dạ Hội Đính Đá Sparkle Pink", "Váy Dạ Hội", "M", "Hồng", 450000, 2000000, "https://images.unsplash.com/photo-1549064482-6779ba3292fe?auto=format&fit=crop&q=80&w=600", "Sẵn sàng")
        ]
        cursor.executemany('''
        INSERT INTO dresses (name, category, size, color, price, deposit, image_url, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', dresses_data)
        
        # Seed lịch đặt mẫu
        bookings_data = [
            (1, "Nguyễn Thu Thảo", "0982345678", "2026-07-01", "2026-07-03", 1600000, "Đã trả", "Đã thanh toán hết"),
            (2, "Lê Hồng Nhung", "0912345678", "2026-07-07", "2026-07-09", 700000, "Đang thuê", "Đã thanh toán hết"),
            (3, "Trần Hải Yến", "0332699103", "2026-07-12", "2026-07-14", 600000, "Chờ duyệt", "Đã cọc"),
            (5, "Phạm Minh Thư", "0966778899", "2026-07-25", "2026-07-26", 400000, "Chờ duyệt", "Đã thanh toán hết")
        ]
        cursor.executemany('''
        INSERT INTO bookings (dress_id, customer_name, customer_phone, start_date, end_date, total_price, status, payment_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', bookings_data)
        
        conn.commit()
        conn.close()
        print("[+] Đã khởi tạo SQLite database: rental_shop.db thành công.")

@app.route('/demo')
def demo_client():
    return render_template('demo.html')

@app.route('/demo/admin')
def demo_admin():
    return render_template('demo_admin.html')

@app.route('/api/demo/dresses')
def api_demo_dresses():
    category = request.args.get('category', 'all')
    size = request.args.get('size', 'all')
    conn = sqlite3.connect(RENTAL_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM dresses WHERE 1=1"
    params = []
    if category != 'all':
        query += " AND category = ?"
        params.append(category)
    if size != 'all':
        query += " AND size = ?"
        params.append(size)
        
    cursor.execute(query, params)
    dresses = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(dresses)

@app.route('/api/demo/proxy-image')
def api_demo_proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return 'Missing image URL', 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        res = requests.get(img_url, headers=headers, timeout=10)
        if res.status_code == 200:
            return Response(res.content, mimetype=res.headers.get('Content-Type', 'image/jpeg'))
        else:
            return redirect('https://images.unsplash.com/photo-1594552072238-b8a33785b261?auto=format&fit=crop&q=80&w=600')
    except Exception as e:
        return redirect('https://images.unsplash.com/photo-1594552072238-b8a33785b261?auto=format&fit=crop&q=80&w=600')

@app.route('/api/demo/bookings', methods=['POST'])
def api_demo_create_booking():
    data = request.json
    dress_id = data.get('dress_id')
    customer_name = data.get('customer_name')
    customer_phone = data.get('customer_phone')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    total_price = data.get('total_price')
    
    if not all([dress_id, customer_name, customer_phone, start_date, end_date]):
        return jsonify({'success': False, 'message': 'Thiếu thông tin đặt lịch.'}), 400
        
    conn = sqlite3.connect(RENTAL_DB)
    cursor = conn.cursor()
    
    # Kiểm tra trùng lịch đặt
    cursor.execute('''
        SELECT COUNT(*) FROM bookings 
        WHERE dress_id = ? 
        AND status != 'Đã trả' 
        AND NOT (end_date < ? OR start_date > ?)
    ''', (dress_id, start_date, end_date))
    
    count = cursor.fetchone()[0]
    if count > 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Váy này đã có lịch thuê trong khoảng thời gian đã chọn.'})
        
    # Tạo đơn đặt lịch
    cursor.execute('''
        INSERT INTO bookings (dress_id, customer_name, customer_phone, start_date, end_date, total_price, status, payment_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (dress_id, customer_name, customer_phone, start_date, end_date, total_price, 'Chờ duyệt', 'Đã cọc'))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đặt lịch thành công!'})

@app.route('/api/demo/admin/bookings')
def api_demo_admin_bookings():
    conn = sqlite3.connect(RENTAL_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.*, d.name as dress_name, d.image_url as dress_image, d.price as dress_price 
        FROM bookings b
        JOIN dresses d ON b.dress_id = d.id
        ORDER BY b.start_date DESC
    ''')
    bookings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(bookings)

@app.route('/api/demo/admin/bookings/<int:booking_id>/status', methods=['POST'])
def api_demo_update_booking_status(booking_id):
    data = request.json
    new_status = data.get('status')
    payment_status = data.get('payment_status')
    
    conn = sqlite3.connect(RENTAL_DB)
    cursor = conn.cursor()
    
    # Lấy thông tin đơn
    cursor.execute('SELECT dress_id FROM bookings WHERE id = ?', (booking_id,))
    booking = cursor.fetchone()
    if not booking:
        conn.close()
        return jsonify({'success': False, 'message': 'Không tìm thấy đơn đặt.'}), 404
        
    dress_id = booking[0]
    
    # Cập nhật trạng thái đặt lịch
    if new_status and payment_status:
        cursor.execute('UPDATE bookings SET status = ?, payment_status = ? WHERE id = ?', (new_status, payment_status, booking_id))
    elif new_status:
        cursor.execute('UPDATE bookings SET status = ? WHERE id = ?', (new_status, booking_id))
    elif payment_status:
        cursor.execute('UPDATE bookings SET payment_status = ? WHERE id = ?', (payment_status, booking_id))
        
    # Cập nhật trạng thái váy tương ứng
    if new_status == 'Đang thuê':
        cursor.execute('UPDATE dresses SET status = "Đang thuê" WHERE id = ?', (dress_id,))
    elif new_status == 'Đã trả':
        cursor.execute('UPDATE dresses SET status = "Sẵn sàng" WHERE id = ?', (dress_id,))
        
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cập nhật trạng thái thành công!'})

@app.route('/api/demo/admin/stats')
def api_demo_admin_stats():
    conn = sqlite3.connect(RENTAL_DB)
    cursor = conn.cursor()
    
    # Tổng doanh thu (Đơn đã thanh toán hết hoặc đã trả)
    cursor.execute("SELECT SUM(total_price) FROM bookings WHERE status = 'Đã trả' OR payment_status = 'Đã thanh toán hết'")
    total_rev = cursor.fetchone()[0] or 0
    
    # Đơn đang hoạt động (Đang thuê + Chờ duyệt)
    cursor.execute("SELECT COUNT(*) FROM bookings WHERE status IN ('Đang thuê', 'Chờ duyệt')")
    active_count = cursor.fetchone()[0] or 0
    
    # Váy sẵn sàng
    cursor.execute("SELECT COUNT(*) FROM dresses WHERE status = 'Sẵn sàng'")
    available_dresses = cursor.fetchone()[0] or 0
    
    # Thống kê doanh thu theo tháng
    chart_data = {
        'labels': ['Tháng 5', 'Tháng 6', 'Tháng 7'],
        'data': [4500000, 7200000, total_rev]
    }
    
    conn.close()
    return jsonify({
        'total_revenue': total_rev,
        'active_bookings': active_count,
        'available_dresses': available_dresses,
        'chart_data': chart_data
    })

@app.route('/api/demo/admin/dresses', methods=['POST'])
def api_demo_add_dress():
    name = request.form.get('name')
    category = request.form.get('category')
    size = request.form.get('size')
    color = request.form.get('color')
    price = request.form.get('price')
    deposit = request.form.get('deposit')
    
    if not all([name, category, size, color, price, deposit]):
        return jsonify({'success': False, 'message': 'Thiếu thông tin váy.'}), 400
        
    image_file = request.files.get('image')
    image_url = 'https://images.unsplash.com/photo-1594552072238-b8a33785b261?auto=format&fit=crop&q=80&w=600' # default
    
    if image_file:
        filename = secure_filename(image_file.filename)
        filename_parts = os.path.splitext(filename)
        filename = f"{filename_parts[0]}_{int(time.time())}{filename_parts[1]}"
        
        save_dir = os.path.join('static', 'uploads')
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)
        image_file.save(filepath)
        image_url = f"/static/uploads/{filename}"
        
    conn = sqlite3.connect(RENTAL_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO dresses (name, category, size, color, price, deposit, image_url, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Sẵn sàng')
    ''', (name, category, size, color, int(price), int(deposit), image_url))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Thêm váy mới thành công!'})

@app.route('/api/demo/admin/dresses/<int:dress_id>', methods=['DELETE'])
def api_demo_delete_dress(dress_id):
    conn = sqlite3.connect(RENTAL_DB)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM bookings WHERE dress_id = ? AND status = 'Đang thuê'", (dress_id,))
    active_count = cursor.fetchone()[0]
    if active_count > 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Không thể xóa váy đang trong quá trình cho thuê.'}), 400
        
    cursor.execute('DELETE FROM dresses WHERE id = ?', (dress_id,))
    cursor.execute('DELETE FROM bookings WHERE dress_id = ?', (dress_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa váy thành công!'})

if __name__ == '__main__':
    # Khởi tạo database nếu chưa tồn tại trước khi chạy server
    init_db_if_not_exists()
    app.run(host='0.0.0.0', port=5000, debug=True)
