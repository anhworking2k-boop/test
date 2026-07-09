#!/usr/bin/env python3
import argparse
import csv
import re
import sys
import time
from urllib.parse import urlparse, quote_plus
import requests
from bs4 import BeautifulSoup
import urllib3

# Vô hiệu hóa cảnh báo SSL không an toàn (để quét các web cũ có SSL lỗi)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def search_duckduckgo(query, limit=30):
    """
    Tìm kiếm trên DuckDuckGo Lite (không yêu cầu JS, dễ cào hơn Google)
    """
    print(f"[*] Đang tìm kiếm trên DuckDuckGo với từ khóa: '{query}'...")
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[!] Lỗi kết nối tới DuckDuckGo (Status: {response.status_code})")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        
        # DuckDuckGo Lite chứa kết quả trong các thẻ class 'result__url' hoặc 'result__snippet'
        for a in soup.find_all('a', class_='result__url'):
            href = a.get('href')
            if href:
                # Làm sạch link nếu cần
                parsed_href = urlparse(href)
                # Đôi khi DDG redirect qua link nội bộ, cần extract ra
                if 'duckduckgo.com/l/?kh=' in href:
                    # Lấy phần redirect thực tế
                    match = re.search(r'uddg=([^&]+)', href)
                    if match:
                        from urllib.parse import unquote
                        href = unquote(match.group(1))
                
                # Chỉ lấy link http/https và loại bỏ chính duckduckgo
                if href.startswith('http') and 'duckduckgo.com' not in href:
                    links.append(href)
                    if len(links) >= limit:
                        break
                        
        print(f"[+] Tìm thấy {len(links)} kết quả từ công cụ tìm kiếm.")
        return links
    except Exception as e:
        print(f"[!] Lỗi khi thực hiện tìm kiếm: {e}")
        return []

def analyze_website(url):
    """
    Tải và phân tích chi tiết HTML của một trang web để phát hiện các yếu tố lỗi thời
    """
    print(f"[*] Đang phân tích: {url}...")
    result = {
        'url': url,
        'domain': urlparse(url).netloc,
        'status': 'Error',
        'title': 'N/A',
        'ssl': 'No',
        'responsive': 'No',
        'table_layout': 'No',
        'obsolete_tags': 'None',
        'jquery_version': 'N/A',
        'copyright_years': 'N/A',
        'score': 0, # Điểm lỗi thời (Càng cao càng lỗi thời, tiềm năng redesign cao)
        'notes': ''
    }
    
    # 1. Kiểm tra SSL
    if url.startswith('https://'):
        result['ssl'] = 'Yes'
        
    try:
        # Tắt kiểm tra SSL verify để vẫn đọc được các site cũ bị hỏng SSL
        response = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        result['status'] = f"{response.status_code}"
        
        if response.status_code != 200:
            result['notes'] = f"Status code không phải 200 (nhưng vẫn truy cập được)"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Lấy Tiêu đề (Title)
        if soup.title and soup.title.string:
            result['title'] = soup.title.string.strip()
            
        # 2. Kiểm tra Responsive (Hỗ trợ thiết bị di động)
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport and 'width=device-width' in str(viewport.get('content', '')):
            result['responsive'] = 'Yes'
        else:
            result['responsive'] = 'No'
            result['score'] += 40  # Không có Responsive là điểm cộng cực lớn cho redesign
            result['notes'] += "Không Responsive; "

        # 3. Kiểm tra Table Layout (Dùng bảng làm khung trang)
        # Trang web hiện đại rất ít khi lạm dụng thẻ table cho layout tổng thể
        tables = soup.find_all('table')
        if len(tables) > 4:
            # Kiểm tra xem có cấu trúc table lồng nhau phổ biến ở web cổ
            nested_tables = False
            for t in tables:
                if t.find('table'):
                    nested_tables = True
                    break
            if nested_tables:
                result['table_layout'] = 'Yes'
                result['score'] += 20
                result['notes'] += "Sử dụng Table Layout; "

        # 4. Tìm các thẻ HTML lỗi thời (obsolete tags)
        obsolete_found = []
        for tag in ['font', 'center', 'frame', 'frameset', 'marquee', 'blink', 'nobr']:
            if soup.find(tag):
                obsolete_found.append(tag)
        if obsolete_found:
            result['obsolete_tags'] = ', '.join(obsolete_found)
            result['score'] += 10 * len(obsolete_found)
            result['notes'] += f"Thẻ cổ: {result['obsolete_tags']}; "

        # 5. Kiểm tra phiên bản jQuery
        jquery_ver = 'N/A'
        for script in soup.find_all('script', src=True):
            src = script['src'].lower()
            match = re.search(r'jquery[.-]([0-9.]+)', src)
            if match:
                jquery_ver = match.group(1)
                result['jquery_version'] = jquery_ver
                # Thường jquery 1.x hoặc 2.x là rất cũ (khoảng năm 2010-2016)
                if jquery_ver.startswith(('1.', '2.')):
                    result['score'] += 15
                    result['notes'] += f"jQuery cũ ({jquery_ver}); "
                break

        # 6. Tìm năm Copyright (Bản quyền) trong footer/HTML
        # Biểu thức chính quy tìm: Copyright / © / (c) đi kèm năm 19xx hoặc 20xx
        html_text = response.text
        copyright_pattern = re.compile(r'(?:copyright|©|\(c\))\s*(?:19\d{2}|20\d{2})\s*(?:-\s*(?:19\d{2}|20\d{2}))?', re.IGNORECASE)
        matches = copyright_pattern.findall(html_text)
        
        # Nếu không tìm thấy, thử tìm riêng năm lẻ Loi ở chân trang
        if not matches:
            # Tìm cụm từ foot/footer chứa số năm 4 chữ số
            footer_text = ""
            for footer_tag in ['footer', 'div']:
                tag_elm = soup.find(footer_tag, class_=re.compile(r'foot|copy', re.I)) or soup.find(footer_tag, id=re.compile(r'foot|copy', re.I))
                if tag_elm:
                    footer_text += tag_elm.get_text()
            
            year_matches = re.findall(r'\b(20[0-2]\d|19\d{2})\b', footer_text)
            if year_matches:
                matches = year_matches

        if matches:
            # Lọc ra các số năm có 4 chữ số từ các khớp
            years = []
            for m in matches:
                found_years = re.findall(r'\b(20[0-2]\d|19\d{2})\b', m)
                years.extend([int(y) for y in found_years])
            
            if years:
                latest_year = max(years)
                result['copyright_years'] = str(latest_year)
                
                # Nếu năm copyright mới nhất nhỏ hơn 2020 chứng tỏ website bị bỏ bê lâu năm
                current_year = time.localtime().tm_year
                diff = current_year - latest_year
                if diff > 5:
                    result['score'] += min(diff * 5, 25) # Cộng tối đa 25 điểm
                    result['notes'] += f"Bản quyền cũ ({latest_year}); "
        
        # Đánh giá tổng quan tiềm năng Redesign
        if result['ssl'] == 'No':
            result['score'] += 10
            result['notes'] += "Không SSL; "
            
        print(f"[+] Hoàn thành phân tích {result['domain']}. Điểm lỗi thời: {result['score']}/100")
        
    except requests.exceptions.Timeout:
        result['status'] = 'Timeout'
        result['notes'] = 'Timeout kết nối'
    except requests.exceptions.SSLError:
        result['status'] = 'SSL Error'
        result['notes'] = 'Lỗi chứng chỉ bảo mật SSL'
    except Exception as e:
        result['status'] = 'Failed'
        result['notes'] = f"Lỗi khác: {str(e)}"
        
    return result

def main():
    parser = argparse.ArgumentParser(description="Outdated Website Finder - Công cụ tìm website cũ lỗi thời để redesign")
    parser.add_argument('-q', '--query', type=str, help="Từ khóa tìm kiếm (kèm Google Dorks nếu muốn, ví dụ: 'site:.vn \"© 2012\" cafe')")
    parser.add_argument('-f', '--file', type=str, help="Đường dẫn tới file txt chứa danh sách tên miền cần kiểm tra (mỗi dòng 1 tên miền)")
    parser.add_argument('-o', '--output', type=str, default='potential_sites.csv', help="Tên file CSV đầu ra (mặc định: potential_sites.csv)")
    parser.add_argument('-l', '--limit', type=int, default=20, help="Số lượng kết quả tối đa cần quét khi dùng chế độ tìm kiếm (mặc định: 20)")
    parser.add_argument('-d', '--delay', type=float, default=2.0, help="Thời gian chờ giữa các lượt quét (giây) để tránh bị chặn (mặc định: 2.0)")
    
    args = parser.parse_args()
    
    if not args.query and not args.file:
        print("[!] Lỗi: Bạn phải chỉ định từ khóa tìm kiếm (-q) HOẶC file chứa danh sách tên miền (-f).")
        parser.print_help()
        sys.exit(1)
        
    urls_to_scan = []
    
    # TH1: Lấy URL từ tìm kiếm DuckDuckGo
    if args.query:
        urls_to_scan = search_duckduckgo(args.query, limit=args.limit)
        
    # TH2: Lấy URL từ file text người dùng cung cấp
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                for line in f:
                    domain = line.strip()
                    if domain:
                        if not domain.startswith(('http://', 'https://')):
                            # Mặc định thêm http để quét
                            urls_to_scan.append(f"http://{domain}")
                        else:
                            urls_to_scan.append(domain)
            print(f"[+] Đã đọc {len(urls_to_scan)} tên miền từ file '{args.file}'.")
        except Exception as e:
            print(f"[!] Lỗi khi đọc file '{args.file}': {e}")
            sys.exit(1)
            
    if not urls_to_scan:
        print("[!] Không tìm thấy URL nào để quét. Tiến trình dừng lại.")
        sys.exit(0)
        
    print(f"\n[*] Bắt đầu quét và phân tích {len(urls_to_scan)} website...")
    results = []
    
    for i, url in enumerate(urls_to_scan):
        # Tạo khoảng nghỉ để tránh bị block IP
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)
            
        res = analyze_website(url)
        results.append(res)
        
    # Sắp xếp kết quả theo điểm số lỗi thời giảm dần (tiềm năng nhất lên đầu)
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # Ghi kết quả ra file CSV
    fieldnames = ['domain', 'url', 'title', 'status', 'ssl', 'responsive', 'table_layout', 'obsolete_tags', 'jquery_version', 'copyright_years', 'score', 'notes']
    
    try:
        with open(args.output, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                # Chỉ lưu các cột có trong fieldnames
                filtered_r = {k: r[k] for k in fieldnames}
                writer.writerow(filtered_r)
        print(f"\n[+++] Đã xuất thành công danh sách tiềm năng ra file: {args.output}")
        print(f"[i] Các website tiềm năng nhất (điểm cao nhất) đã được xếp trên đầu.")
    except Exception as e:
        print(f"[!] Lỗi khi ghi file CSV: {e}")

if __name__ == '__main__':
    main()
