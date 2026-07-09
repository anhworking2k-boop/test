#!/usr/bin/env python3
import csv
import os
import re
import sys
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import urllib3

# Vô hiệu hóa cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_url(url):
    """Làm sạch và định dạng URL"""
    if not url:
        return ''
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return f"http://{url}"
    return url

def is_vietnamese_lead(name, phone, website, address):
    """
    Kiểm tra xem thông tin doanh nghiệp có thuộc Việt Nam hay không
    """
    addr_lower = str(address).lower() if address else ''
    phone_str = str(phone).strip() if phone else ''
    
    # Loại trừ ngay nếu có địa chỉ hoặc số điện thoại nước ngoài rõ ràng
    if any(k in addr_lower for k in [', usa', 'united states', 'new york', ' ny ', ', ny', 'london,', ', uk', 'singapore']):
        return False
    if phone_str.startswith(('+1', '+44', '+65', '+61')) and not phone_str.startswith(('+84')):
        return False

    # 1. Kiểm tra qua địa chỉ
    if any(k in addr_lower for k in ['việt nam', 'vietnam', 'hà nội', 'hanoi', 'hồ chí minh', 'sài gòn', 'saigon', 'đà nẵng', 'danang', 'tphcm', 'quận', 'phường', 'đường', 'thành phố']):
        return True
        
    # 2. Kiểm tra qua số điện thoại (bắt đầu bằng +84, 03, 05, 07, 08, 09, hoặc 02/01)
    if phone_str.startswith(('+84', '03', '05', '07', '08', '09', '02', '01')):
        return True
        
    # 3. Kiểm tra tên miền website
    web_lower = str(website).lower() if website else ''
    if any(web_lower.endswith(ext) for ext in ['.vn', '.com.vn', '.net.vn', '.org.vn', '.edu.vn', '.gov.vn']):
        return True
        
    # 4. Kiểm tra qua ngôn ngữ tên doanh nghiệp (các từ tiếng Việt không dấu/có dấu phổ biến)
    name_lower = str(name).lower() if name else ''
    vn_keywords = ['công ty', 'tnhh', 'cổ phần', 'khách sạn', 'nhà hàng', 'cà phê', 'quán', 'tiệm', 'spa', 'thẩm mỹ', 'phòng khám', 'dịch vụ', 'du lịch', 'hotel', 'restaurant', 'cafe']
    if any(k in name_lower for k in vn_keywords):
        return True
        
    return False

def classify_category(name):
    """
    Tự động phân loại doanh nghiệp vào 5 nhóm ngách chính dựa trên tên gọi
    """
    name_lower = str(name).lower() if name else ''
    
    # 1. Khách sạn / Homestay
    if any(k in name_lower for k in ['khách sạn', 'hotel', 'homestay', 'villa', 'resort', 'nhà nghỉ', 'nhà khách', 'accommodation', 'stay']):
        return 'Khách sạn / Homestay'
        
    # 2. Nha khoa / Spa
    if any(k in name_lower for k in ['nha khoa', 'dental', 'spa', 'thẩm mỹ', 'clinic', 'phòng khám', 'massage', 'làm đẹp', 'beauty', 'dentist', 'skin']):
        return 'Nha khoa / Spa'
        
    # 3. Dịch vụ tại nhà
    if any(k in name_lower for k in ['sửa', 'điều hòa', 'cống', 'chuyển nhà', 'hút bể phốt', 'điện nước', 'sửa chữa', 'repair', 'plumbing', 'clean', 'vệ sinh']):
        return 'Dịch vụ tại nhà'
        
    # 4. Luật / Kế toán
    if any(k in name_lower for k in ['luật', 'luật sư', 'lawyer', 'kế toán', 'thuế', 'kiểm toán', 'tư vấn pháp luật', 'law', 'accounting', 'audit', 'tax']):
        return 'Luật / Kế toán'
        
    # 5. Giáo dục / Trung tâm
    if any(k in name_lower for k in ['trường', 'mầm non', 'ngoại ngữ', 'tiếng anh', 'trung tâm', 'dạy học', 'học viện', 'school', 'academy', 'english', 'center', 'education']):
        return 'Giáo dục / Trung tâm'
        
    # 6. Studio ảnh cưới
    if any(k in name_lower for k in ['studio', 'wedding', 'bridal', 'cưới', 'chụp ảnh', 'áo cưới', 'ảnh viện']):
        return 'Studio ảnh cưới'
        
    return 'Khác'

def analyze_lead_website(url):
    """Phân tích nhanh website doanh nghiệp để đánh giá độ lỗi thời"""
    url = clean_url(url)
    result = {
        'status': 'Error',
        'responsive': 'No',
        'ssl': 'No',
        'copyright_years': 'N/A',
        'score': 0,
        'notes': ''
    }
    
    if not url:
        return result
        
    if url.startswith('https://'):
        result['ssl'] = 'Yes'
        
    try:
        # Request nhanh với timeout ngắn (8 giây)
        response = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        result['status'] = f"{response.status_code}"
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Kiểm tra responsive
            viewport = soup.find('meta', attrs={'name': 'viewport'})
            if viewport and 'width=device-width' in str(viewport.get('content', '')):
                result['responsive'] = 'Yes'
            else:
                result['responsive'] = 'No'
                result['score'] += 40
                result['notes'] += "Không Responsive; "
                
            # Kiểm tra Table layout
            tables = soup.find_all('table')
            if len(tables) > 4:
                result['score'] += 20
                result['notes'] += "Table Layout; "
                
            # Kiểm tra Copyright
            html_text = response.text
            copyright_pattern = re.compile(r'(?:copyright|©|\(c\))\s*(?:19\d{2}|20\d{2})\s*(?:-\s*(?:19\d{2}|20\d{2}))?', re.IGNORECASE)
            matches = copyright_pattern.findall(html_text)
            if matches:
                years = []
                for m in matches:
                    found_years = re.findall(r'\b(20[0-2]\d|19\d{2})\b', m)
                    years.extend([int(y) for y in found_years])
                if years:
                    latest_year = max(years)
                    result['copyright_years'] = str(latest_year)
                    diff = 2026 - latest_year
                    if diff > 5:
                        result['score'] += min(diff * 5, 25)
                        result['notes'] += f"Bản quyền cũ ({latest_year}); "
                        
            if result['ssl'] == 'No':
                result['score'] += 15
                result['notes'] += "Không SSL; "
        else:
            result['notes'] = f"Lỗi truy cập (Status code: {response.status_code})"
            
    except requests.exceptions.Timeout:
        result['status'] = 'Timeout'
        result['notes'] = 'Timeout kết nối'
    except Exception as e:
        result['status'] = 'Failed'
        result['notes'] = f"Không kết nối được: {str(e)}"
        
    return result

def detect_headers(headers):
    """
    Tự động nhận diện các cột trong file CSV quét từ Google Maps
    """
    detected = {
        'name': None,
        'phone': None,
        'website': None,
        'address': None
    }
    
    for h in headers:
        h_clean = h.lower().strip()
        
        # Nhận diện cột Tên doanh nghiệp
        if any(k in h_clean for k in ['name', 'title', 'company', 'doanh nghiệp', 'tên', 'cửa hàng', 'khách sạn', 'nhà hàng']):
            if not detected['name']: detected['name'] = h
            
        # Nhận diện cột Số điện thoại
        elif any(k in h_clean for k in ['phone', 'tel', 'sđt', 'điện thoại', 'contact']):
            if not detected['phone']: detected['phone'] = h
            
        # Nhận diện cột Website
        elif any(k in h_clean for k in ['website', 'site', 'url', 'web', 'link']):
            if not detected['website']: detected['website'] = h
            
        # Nhận diện cột Địa chỉ
        elif any(k in h_clean for k in ['address', 'location', 'địa chỉ', 'nơi ở', 'địa điểm']):
            if not detected['address']: detected['address'] = h
            
    # Dự phòng nếu không tự phát hiện được
    if not detected['name'] and len(headers) > 0: detected['name'] = headers[0]
    if not detected['phone'] and len(headers) > 1: detected['phone'] = headers[1]
    if not detected['website'] and len(headers) > 2: detected['website'] = headers[2]
    if not detected['address'] and len(headers) > 3: detected['address'] = headers[3]
    
    return detected

def analyze_csv_leads(csv_filepath):
    """
    Đọc file CSV Google Maps, phân loại doanh nghiệp và phân tích website
    """
    if not os.path.exists(csv_filepath):
        return []
        
    leads = []
    
    try:
        # Thử đọc bằng UTF-8-SIG (để loại bỏ BOM của Excel nếu có)
        with open(csv_filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            headers = next(reader)
            
            detected = detect_headers(headers)
            
            # Tạo DictReader để dễ đọc theo tên cột
            f.seek(0)
            dict_reader = csv.DictReader(f)
            
            for row in dict_reader:
                name = row.get(detected['name'], '').strip()
                phone = row.get(detected['phone'], '').strip()
                website = row.get(detected['website'], '').strip()
                address = row.get(detected['address'], '').strip()
                
                # Bỏ qua nếu dòng trống tên
                if not name:
                    continue
                    
                # Lọc chỉ lấy các lead thuộc Việt Nam
                if not is_vietnamese_lead(name, phone, website, address):
                    continue
                    
                # Tính toán điểm cộng/trừ ưu tiên bán hàng (Chỉ số chốt nhanh)
                score_adj = 0
                
                # A. Điểm cộng cho SĐT Di động (Dễ add Zalo chat trực tiếp với chủ)
                phone_clean = ''.join(c for c in str(phone) if c.isdigit())
                is_mobile = False
                if phone_clean.startswith('84') and len(phone_clean) >= 11:
                    prefix = phone_clean[2:4]
                    if prefix in ['90', '91', '92', '93', '94', '96', '97', '98', '99', '32', '33', '34', '35', '36', '37', '38', '39', '70', '76', '77', '78', '79', '81', '82', '83', '84', '85', '86', '88', '89', '56', '58', '59']:
                        is_mobile = True
                elif phone_clean.startswith('0') and len(phone_clean) >= 10:
                    prefix = phone_clean[1:3]
                    if prefix in ['90', '91', '92', '93', '94', '96', '97', '98', '99', '32', '33', '34', '35', '36', '37', '38', '39', '70', '76', '77', '78', '79', '81', '82', '83', '84', '85', '86', '88', '89', '56', '58', '59']:
                        is_mobile = True
                        
                if is_mobile:
                    score_adj += 15
                    
                # B. Điểm cộng cho quy mô nhỏ/mini dễ tiếp cận
                name_lower = name.lower()
                small_biz_keywords = ['homestay', 'spa mini', 'tiệm', 'xưởng', 'phòng khám', 'luật sư', 'nhà nghỉ', 'cửa hàng', 'sửa chữa', 'điện lạnh', 'điện nước']
                if any(k in name_lower for k in small_biz_keywords):
                    score_adj += 10
                    
                # C. Điểm trừ cho doanh nghiệp lớn/công vụ khó tiếp cận
                big_org_keywords = ['bệnh viện', 'tập đoàn', 'hệ thống', 'chuỗi', 'quốc tế', 'trường học', 'trường đại học', 'học viện', 'nhà khách', 'công ty cổ phần']
                if any(k in name_lower for k in big_org_keywords):
                    score_adj -= 20

                lead_info = {
                    'name': name,
                    'phone': phone,
                    'website': website,
                    'address': address,
                    'category': classify_category(name),
                    'type': 'No Website', # 'No Website', 'Dead Website', 'Outdated Website', 'Modern Website'
                    'status': 'N/A',
                    'responsive': 'N/A',
                    'ssl': 'N/A',
                    'copyright_years': 'N/A',
                    'score': 100 + score_adj, # Doanh nghiệp không web có độ ưu tiên cao nhất
                    'notes': 'Chưa có website. Cơ hội bán Web mới!'
                }
                
                # 1. Doanh nghiệp không có website
                if not website or website.lower() in ['n/a', 'none', 'null', 'không có']:
                    leads.append(lead_info)
                    
                # 2. Doanh nghiệp có website -> tiến hành quét
                else:
                    web_analysis = analyze_lead_website(website)
                    lead_info.update(web_analysis)
                    
                    # Phân loại dựa trên kết quả phân tích
                    if web_analysis['status'] in ['Timeout', 'Failed'] or (web_analysis['status'] != '200' and int(web_analysis['status']) >= 400):
                        lead_info['type'] = 'Dead Website'
                        lead_info['score'] = 80 + score_adj # Web chết có độ ưu tiên cao thứ 2
                        lead_info['notes'] = f"Website bị hỏng/không truy cập được ({web_analysis['notes']}). Cơ hội sửa/thiết kế lại!"
                    else:
                        # Web hoạt động bình thường, kiểm tra điểm lỗi thời
                        if web_analysis['score'] >= 40:
                            lead_info['type'] = 'Outdated Website'
                            lead_info['score'] = web_analysis['score'] + score_adj
                            lead_info['notes'] = f"Web lỗi thời ({web_analysis['notes']}). Cơ hội chào dịch vụ Redesign!"
                        else:
                            lead_info['type'] = 'Modern Website'
                            lead_info['score'] = 15 + score_adj
                            lead_info['notes'] = 'Website hiện đại. Điểm lỗi thời thấp.'
                            
                    leads.append(lead_info)
                    
        # Lưu kết quả ra file báo cáo chung
        output_file = 'local_leads_report.csv'
        fieldnames = ['name', 'phone', 'website', 'address', 'category', 'type', 'status', 'responsive', 'ssl', 'copyright_years', 'score', 'notes']
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            # Sắp xếp theo score giảm dần (ưu tiên cao nhất lên đầu)
            for r in sorted(leads, key=lambda x: x['score'], reverse=True):
                writer.writerow(r)
                
        print(f"[+] Phân tích thành công {len(leads)} leads Việt Nam từ file CSV.")
        return leads
    except Exception as e:
        print(f"[!] Lỗi khi phân tích file CSV: {e}")
        return []

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Sử dụng: ./lead_analyzer.py <du_lieu_google_maps.csv>")
        sys.exit(1)
        
    analyze_csv_leads(sys.argv[1])
