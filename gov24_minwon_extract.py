import csv
from bs4 import BeautifulSoup
import requests
import os
import re
import time
import urllib.parse
import json
from datetime import datetime
import concurrent.futures
import threading
from queue import Queue
from urllib.parse import urlparse
import pandas as pd
import nltk
from nltk.tokenize import word_tokenize
from collections import Counter
import hashlib
import difflib

# 전역 변수로 세션 관리 - 연결 재사용
session = requests.Session()
# 요청 헤더 설정 - 브라우저처럼 보이게
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
})

# 스레드 로컬 스토리지 - 스레드별 세션 관리
thread_local = threading.local()

def get_session():
    """각 스레드마다 개별 세션을 생성하여 반환"""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        })
    return thread_local.session

def extract_minwon_list(html_content):
    """정부24 웹페이지에서 민원 목록을 추출하는 함수"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 민원 목록이 있는 li 요소들을 찾습니다 - 실제 HTML 구조 반영
    minwon_items = soup.select('li.result_li_box')
    
    minwon_list = []
    
    for item in minwon_items:
        try:
            # 민원 이름
            title_element = item.select_one('a.list_font17')
            title = title_element.text.strip() if title_element else "제목 없음"
            
            # 민원 링크 URL
            link = title_element.get('href', '') if title_element else ""
            
            # 민원 설명
            desc_element = item.select_one('p.list_info_txt')
            description = desc_element.text.strip() if desc_element else "설명 없음"
            
            # 담당 부서/기관
            dept_element = item.select_one('span.division_')
            department = dept_element.text.strip() if dept_element else "부서 정보 없음"
            
            # 인증 필요 여부
            auth_element = item.select_one('span.confi_')
            auth_required = auth_element.text.strip() if auth_element else "정보 없음"
            
            # 민원 유형 (민원, 정부서비스 등)
            badge_element = item.select_one('span.badge_gray')
            badge = badge_element.text.strip() if badge_element else "유형 정보 없음"
            
            # 서비스 버튼 정보
            button_element = item.select_one('a.small_btn')
            button_text = button_element.text.strip() if button_element else "버튼 없음"
            button_onclick = button_element.get('onclick', '') if button_element else ""
            
            # 서비스 ID 및 카테고리 추출 (onclick 속성에서)
            capp_biz_cd = ""
            high_ctg_cd = ""
            tp_seq = ""
            if button_onclick:
                # 예: goUrlNewChk('13100000026', 'A09005', '01')
                match = re.search(r"goUrlNewChk\('([^']+)',\s*'([^']+)',\s*'([^']+)'", button_onclick)
                if match:
                    capp_biz_cd = match.group(1)
                    high_ctg_cd = match.group(2)
                    tp_seq = match.group(3)
            
            minwon_list.append({
                "민원명": title,
                "설명": description,
                "담당부서": department,
                "인증필요": auth_required,
                "유형": badge,
                "링크": link,
                "링크텍스트": button_text,
                "서비스ID": capp_biz_cd,
                "카테고리": high_ctg_cd,
                "일련번호": tp_seq
            })
        except Exception as e:
            print(f"민원 항목 처리 중 오류 발생: {str(e)}")
            continue
    
    return minwon_list

def get_last_page_number(html_content):
    """HTML에서 마지막 페이지 번호를 추출하는 함수"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    try:
        # 총 개수 정보 추출
        total_count_element = soup.select_one('.new_h20 em.font_eb193a')
        if total_count_element:
            total_text = total_count_element.text.strip().replace(',', '')
            if total_text.isdigit():
                total_count = int(total_text)
                # 페이지당 10개 항목이 표시된다고 가정
                return (total_count + 9) // 10
    
        # 페이지네이션 영역 찾기
        pagination = soup.select_one('div.pagination_box')
        
        if pagination:
            # 마지막 페이지로 이동하는 버튼 찾기
            last_page_link = pagination.select_one('li.page_last a')
            if last_page_link and 'onclick' in last_page_link.attrs:
                onclick_attr = last_page_link['onclick']
                # applySetPage('1151.0')와 같은 형식에서 숫자 추출
                match = re.search(r"applySetPage\('(\d+\.?\d*)'\)", onclick_attr)
                if match:
                    return int(float(match.group(1)))
        
        # 페이지 번호를 찾지 못한 경우 페이지네이션의 마지막 숫자 링크 시도
        page_links = pagination.select('li.pageList a') if pagination else []
        if page_links:
            try:
                last_page = max([int(link.text) for link in page_links if link.text.isdigit()])
                return last_page
            except:
                pass
    except Exception as e:
        print(f"마지막 페이지 번호 추출 중 오류: {str(e)}")
    
    # 기본값으로 1 반환 (최소 1페이지는 있음)
    return 1

def get_page_url(base_url, page_number):
    """페이지 번호에 해당하는 URL을 생성하는 함수"""
    if '?' in base_url:
        if 'pageIndex=' in base_url:
            # 이미 pageIndex 파라미터가 있는 경우 교체
            return re.sub(r'pageIndex=\d+', f'pageIndex={page_number}', base_url)
        else:
            # 다른 파라미터가 있고 pageIndex가 없는 경우 추가
            return f"{base_url}&pageIndex={page_number}"
    else:
        # 파라미터가 없는 경우 새로 추가
        return f"{base_url}?pageIndex={page_number}"

def save_to_csv(minwon_list, filename="정부24_민원목록.csv"):
    """민원 목록을 CSV 파일로 저장하는 함수"""
    desktop_path = os.path.expanduser("~/Desktop/data")
    file_path = os.path.join(desktop_path, filename)
    
    # 상세 정보를 포함한 필드명 목록 (오류여부 필드 추가)
    fieldnames = [
        "민원명", "설명", "담당부서", "인증필요", "유형", "링크", "링크텍스트",
        "처리절차", "신청방법", "필요서류", "수수료", "담당기관", "연락처", 
        "처리기간", "신청자격", "관련법령", "첨부파일", "기타정보", "오류여부"
    ]
    
    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for minwon in minwon_list:
            writer.writerow(minwon)
    
    print(f"CSV 파일이 저장되었습니다: {file_path}")
    return file_path

def extract_detail_info(url, retry_count=2):
    """민원 상세 페이지에서 필요한 정보를 추출하는 함수 - 외부 링크도 처리"""
    detail_info = {
        "처리절차": "",
        "신청방법": "",
        "필요서류": "",
        "수수료": "",
        "담당기관": "",
        "연락처": "",
        "처리기간": "",
        "신청자격": "",
        "관련법령": "",
        "첨부파일": "",
        "기타정보": "",
        "오류여부": "정상"
    }
    
    try:
        # URL 전처리
        if url.startswith('/'):
            url = 'https://www.gov.kr' + url
        elif not url.startswith('http'):
            url = 'https://www.gov.kr/' + url
        
        # URL 파싱
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # 웹사이트 도메인 확인 - 정부 사이트 확인 (gov.kr, go.kr, or.kr 등)
        is_govt_site = any(domain.endswith(suffix) for suffix in ['.gov.kr', '.go.kr', '.or.kr'])
        
        if not is_govt_site:
            # 외부 링크지만 처리는 함
            detail_info["기타정보"] = f"외부 링크 (처리됨): {url}"
            detail_info["신청방법"] = f"외부 사이트({domain})에서 처리하는 민원입니다. 해당 사이트를 방문하세요."
            detail_info["오류여부"] = "외부링크_처리됨"
            return detail_info
        
        # 스레드별 세션 사용
        session = get_session()
        
        # 요청 전송 (타임아웃 설정, 재시도 로직)
        for attempt in range(retry_count + 1):
            try:
                response = session.get(url, timeout=10)  # 타임아웃 10초로 증가
                if response.status_code == 200:
                    break
            except (requests.exceptions.RequestException, Exception) as e:
                if attempt < retry_count:
                    # 재시도
                    time.sleep(1)  # 재시도 간격 증가
                    continue
                else:
                    # 재시도 횟수 초과
                    detail_info["기타정보"] = f"요청 오류: {str(e)[:200]}"
                    detail_info["오류여부"] = "요청오류"
                    return detail_info
        
        # 응답 코드 확인
        if response.status_code != 200:
            detail_info["기타정보"] = f"HTTP 오류: 상태 코드 {response.status_code}"
            detail_info["오류여부"] = f"HTTP{response.status_code}"
            return detail_info
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 서비스 개요 섹션에서 정보 추출
        service_overview = soup.select_one('h3#tit_index_001 ~ div.info_svc_list')
        if service_overview:
            # 서비스 개요 내 항목들 추출
            items = service_overview.select('li')
            for item in items:
                title_elem = item.select_one('p.tit')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                
                # 내용 추출 (텍스트 또는 HTML 구조에 따라)
                content = ""
                content_elem = item.select_one('p.txt') or item.select_one('div.txt_wrap')
                
                if content_elem:
                    # 텍스트 요소만 추출하고 불필요한 공백 제거
                    content = content_elem.get_text(strip=True, separator=' ')
                
                # 각 항목에 따라 적절한 필드에 저장
                if '신청방법' in title:
                    detail_info['신청방법'] = content
                elif '신청자격' in title:
                    detail_info['신청자격'] = content
                elif '구비서류' in title:
                    detail_info['필요서류'] = content
                elif '수수료' in title:
                    detail_info['수수료'] = content
                elif '처리기간' in title:
                    detail_info['처리기간'] = content
                elif '발급서류' in title or '신청서' in title:
                    if not detail_info.get('첨부파일'):
                        detail_info['첨부파일'] = content
        
        # 2. 기본정보 섹션 추출
        basic_info = soup.select_one('h3#tit_index_002 ~ ul.mw_list_dot')
        if basic_info:
            content = basic_info.get_text(strip=True, separator=' ')
            if content and len(content) > 10:
                if not detail_info.get('기타정보'):
                    detail_info['기타정보'] = content[:500] + ('...' if len(content) > 500 else '')
        
        # 3. 처리절차 추출 - 순서가 있는 목록(ol.mw_list_num_round)
        procedure_section = soup.select_one('h3#tit_index_003 ~ ol.mw_list_num_round')
        if procedure_section:
            steps = []
            for step in procedure_section.select('li'):
                step_name = step.select_one('span:not(.num)')
                step_text = step_name.get_text(strip=True) if step_name else ""
                
                # 기관 정보가 있으면 같이 추출
                agencies = step.select('a.mw_btn')
                agency_texts = [agency.get_text(strip=True) for agency in agencies if agency.get_text(strip=True)]
                
                if step_text:
                    if agency_texts:
                        steps.append(f"{step_text}({', '.join(agency_texts)})")
                    else:
                        steps.append(step_text)
            
            if steps:
                detail_info["처리절차"] = ' → '.join(steps)
        
        # 법인 또는 기관 정보 추출 시도
        organizations = []
        org_elements = soup.select('div.org_tit')
        for org_element in org_elements:
            org_name = org_element.get_text(strip=True)
            if org_name:
                organizations.append(org_name)
        
        if organizations:
            detail_info["담당기관"] = ", ".join(organizations)
        
        # 담당기관 정보가 없는 경우 다른 방법으로 추출 시도
        if not detail_info["담당기관"]:
            agency_headers = soup.select('h4.tit_dep_3')
            for header in agency_headers:
                if header and '제도를 담당하는 기관' in header.get_text(strip=True):
                    agency_text = header.get_text(strip=True, separator=' ')
                    if ':' in agency_text:
                        detail_info['담당기관'] = agency_text.split(':', 1)[1].strip()
                    else:
                        # 다음 요소에서 기관명 찾기 시도
                        next_elem = header.find_next()
                        if next_elem:
                            potential_agency = next_elem.get_text(strip=True)
                            if potential_agency and len(potential_agency) < 50:  # 너무 긴 텍스트는 제외
                                detail_info['담당기관'] = potential_agency
                    break
        
        # 5. 근거법령 추출
        legal_basis_headers = soup.select('h4.tit_dep_3')
        for header in legal_basis_headers:
            if header and '근거법령' in header.get_text(strip=True):
                # 해당 헤더의 다음 요소(ul.mw_list_dot)를 찾음
                next_element = header.find_next('ul', class_='mw_list_dot')
                if next_element:
                    laws = []
                    for law in next_element.select('li'):
                        law_text = law.get_text(strip=True, separator=' ')
                        if law_text:
                            laws.append(law_text)
                    
                    if laws:
                        detail_info['관련법령'] = '; '.join(laws)
                break  # 첫 번째 근거법령 섹션만 처리
        
        # 연락처 정보 추출 시도
        contact_info = []
        contact_elements = soup.select('div.customer_info')
        for contact_element in contact_elements:
            contact_text = contact_element.get_text(strip=True, separator=' ')
            if contact_text:
                contact_info.append(contact_text)
        
        if contact_info:
            detail_info["연락처"] = " / ".join(contact_info)
        
        # 서류 다운로드 링크 추출
        download_links = []
        download_elements = soup.select('a.file_download')
        for download_element in download_elements:
            download_text = download_element.get_text(strip=True)
            if download_text:
                download_links.append(download_text)
        
        if download_links:
            detail_info["첨부파일"] = ", ".join(download_links)
        
        # 정보의 빈값 여부 확인 및 추가 처리
        filled_count = sum(1 for v in detail_info.values() if v and v != "정상")
        if filled_count <= 3:  # 충분한 정보가 없는 경우
            # 일반 텍스트 검색 (클래스와 상관없이)
            for keyword, field in [
                ("신청방법", "신청방법"), 
                ("처리기간", "처리기간"),
                ("수수료", "수수료"),
                ("구비서류", "필요서류"),
                ("신청자격", "신청자격"),
                ("담당기관", "담당기관"),
                ("문의처", "연락처"),
                ("관련법령", "관련법령")
            ]:
                if not detail_info.get(field):
                    # 텍스트 포함 요소 찾기 - 더 안전한 방식 사용
                    elements = []
                    for tag in soup.find_all(text=True):
                        if keyword in tag:
                            elements.append(tag)
                    
                    if elements:
                        for elem in elements:
                            parent = elem.parent
                            if parent:
                                # 해당 요소의 부모나 형제 요소에서 값 추출
                                next_elem = parent.find_next()
                                if next_elem:
                                    content = next_elem.get_text(strip=True, separator=' ')
                                    if content and len(content) > 3:
                                        detail_info[field] = content
                                        break
        
        # 일부 필드가 비어있으면 강화된 패턴 매칭 시도
        if not detail_info.get('처리기간'):
            for tag in soup.find_all(['p', 'div', 'span']):
                text = tag.get_text(strip=True)
                if '처리기간' in text and ':' in text:
                    period = text.split(':', 1)[1].strip()
                    if period and len(period) < 50:  # 적절한 길이의 텍스트만
                        detail_info['처리기간'] = period
                        break
        
        # 수수료 정보 추가 탐색
        if not detail_info.get('수수료'):
            for tag in soup.find_all(['p', 'div', 'span']):
                text = tag.get_text(strip=True)
                if '수수료' in text and (':' in text or '원' in text):
                    fee_info = text.split(':', 1)[1].strip() if ':' in text else text
                    if fee_info and len(fee_info) < 100:
                        detail_info['수수료'] = fee_info
                        break
        
        return detail_info
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        detail_info["기타정보"] = f"오류 발생: {str(e)[:200]}"
        detail_info["오류여부"] = "기타오류"
        # 상세 로그 출력
        print(f"상세 추출 중 오류: {str(e)}")
        print(f"URL: {url}")
        print(f"스택 트레이스: {error_trace}")
        return detail_info

def get_department_list(html_content=None):
    """정부24에서 부서 목록을 추출하는 함수"""
    departments = []
    
    # 서버에 직접 요청해서 정보 가져오기
    try:
        if html_content is None:
            # 기본 검색 페이지 URL
            url = "https://www.gov.kr/search/svcmidMw?SVC_DIV=mid"
            response = requests.get(url)
            if response.status_code == 200:
                html_content = response.text
            else:
                print(f"부서 목록 페이지를 불러오는데 실패했습니다. 상태 코드: {response.status_code}")
                return get_default_departments()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 기관 구분 선택 박스 찾기
        dept_select = soup.select_one('select[name="deptIncCd"]')
        
        if dept_select:
            # 모든 옵션 가져오기
            options = dept_select.select('option')
            
            for option in options:
                if 'value' in option.attrs and option['value']:
                    dept_code = option['value']
                    dept_name = option.text.strip()
                    departments.append({
                        'code': dept_code,
                        'name': dept_name
                    })
        
        # 부서 그룹(optgroup) 처리
        optgroups = dept_select.select('optgroup') if dept_select else []
        
        for optgroup in optgroups:
            # 각 그룹 내의 옵션 가져오기
            group_options = optgroup.select('option')
            
            for option in group_options:
                if 'value' in option.attrs and option['value']:
                    dept_code = option['value']
                    dept_name = option.text.strip()
                    group_name = optgroup.get('label', '')
                    departments.append({
                        'code': dept_code,
                        'name': dept_name,
                        'group': group_name
                    })
    
    except Exception as e:
        print(f"부서 목록 추출 중 오류 발생: {str(e)}")
        return get_default_departments()
    
    # 부서 목록이 비어있는 경우 기본 부서 목록 사용
    if not departments:
        return get_default_departments()
    
    return departments

def get_default_departments():
    """기본 부서 목록 반환"""
    return [
        {'code': '1352000', 'name': '보건복지부', 'group': '부'},
        {'code': '1492000', 'name': '고용노동부', 'group': '부'},
        {'code': '1721000', 'name': '과학기술정보통신부', 'group': '부'},
        {'code': '1342000', 'name': '교육부', 'group': '부'},
        {'code': '1290000', 'name': '국방부', 'group': '부'},
        {'code': '1613000', 'name': '국토교통부', 'group': '부'},
        {'code': '1051000', 'name': '기획재정부', 'group': '부'},
        {'code': '1371000', 'name': '문화체육관광부', 'group': '부'},
        {'code': '1270000', 'name': '법무부', 'group': '부'},
        {'code': '1450000', 'name': '산업통상자원부', 'group': '부'},
        {'code': '1383000', 'name': '여성가족부', 'group': '부'},
        {'code': '1262000', 'name': '외교부', 'group': '부'},
        {'code': '1741000', 'name': '행정안전부', 'group': '부'},
        {'code': '1480000', 'name': '환경부', 'group': '부'},
        {'code': '1320000', 'name': '경찰청', 'group': '청'},
        {'code': '1210000', 'name': '국세청', 'group': '청'},
        {'code': '1360000', 'name': '기상청', 'group': '청'},
        {'code': '1300000', 'name': '병무청', 'group': '청'},
        {'code': '1790387', 'name': '질병관리청', 'group': '청'}
    ]

def save_to_combined_csv(all_minwon_data, filename=None):
    """모든 부서의 민원 데이터를 하나의 CSV 파일로 저장하는 함수"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"정부24_민원목록_통합_{timestamp}.csv"
    
    desktop_path = os.path.expanduser("~/Desktop/data")
    file_path = os.path.join(desktop_path, filename)
    
    # 상세 정보를 포함한 필드명 목록 (오류여부 필드 추가)
    fieldnames = [
        "민원명", "설명", "담당부서", "인증필요", "유형", "링크", "링크텍스트",
        "처리절차", "신청방법", "필요서류", "수수료", "담당기관", "연락처", 
        "처리기간", "신청자격", "관련법령", "첨부파일", "기타정보", "수집부서코드", "오류여부"
    ]
    
    total_count = sum(len(data['minwons']) for data in all_minwon_data)
    
    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for dept_data in all_minwon_data:
            for minwon in dept_data['minwons']:
                # 수집 부서 코드 추가
                minwon['수집부서코드'] = dept_data['dept_code']
                writer.writerow(minwon)
    
    print(f"\n통합 CSV 파일이 저장되었습니다: {file_path}")
    print(f"총 {total_count}개 민원 정보가 저장되었습니다.")
    return file_path

def batch_process_minwons(minwon_batch, max_workers=10):
    """민원 목록의 상세 정보를 병렬로 처리하는 함수"""
    results = []
    
    # 최대 작업자 수 재조정 - 너무 많은 동시 요청은 서버에 부담을 줄 수 있음
    effective_workers = min(max_workers, len(minwon_batch), 15)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
        # 병렬로 처리할 작업 목록 생성
        future_to_minwon = {}
        for minwon in minwon_batch:
            # 링크가 상대 경로인 경우 처리
            if minwon.get('링크') and minwon['링크'] != "링크 없음":
                # 서비스ID와 카테고리, 일련번호가 있는 경우 상세 페이지 URL 구성
                if minwon.get('서비스ID') and minwon.get('카테고리') and minwon.get('일련번호'):
                    # 실제 URL 구성
                    detail_url = f"/mw/AA020InfoCappView.do?HighCtgCD={minwon['카테고리']}&CappBizCD={minwon['서비스ID']}&tp_seq={minwon['일련번호']}"
                    minwon['상세페이지'] = detail_url
                future = executor.submit(process_single_minwon, minwon)
                future_to_minwon[future] = minwon
        
        # 진행 상황 표시용 카운터
        completed = 0
        total = len(future_to_minwon)
        
        for future in concurrent.futures.as_completed(future_to_minwon):
            minwon = future_to_minwon[future]
            completed += 1
            
            try:
                processed_minwon = future.result()
                results.append(processed_minwon)
                # 진행 상황 출력 (10%마다)
                if completed % max(1, total // 10) == 0 or completed == total:
                    print(f"처리 중... {completed}/{total} 완료 ({completed/total*100:.1f}%)")
            except Exception as e:
                print(f"민원 처리 중 오류 발생: {minwon.get('민원명', 'Unknown')} - {str(e)}")
                # 오류가 발생해도 일단 원본 데이터 추가
                minwon["오류여부"] = "처리실패"
                minwon["기타정보"] = f"처리 중 예외 발생: {str(e)[:200]}"
                results.append(minwon)
    
    return results

def process_single_minwon(minwon):
    """단일 민원의 상세 정보를 처리하는 함수"""
    detail_url = minwon.get('상세페이지') or minwon.get('링크')
    
    if detail_url and detail_url != "링크 없음":
        detail_info = extract_detail_info(detail_url)
        minwon.update(detail_info)
    else:
        minwon["오류여부"] = "링크없음"
    
    return minwon

def fetch_pages_parallel(base_url, last_page, max_workers=5):
    """페이지 데이터를 병렬로 가져오는 함수"""
    all_minwons = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 각 페이지 URL 생성
        page_urls = [(get_page_url(base_url, page), page) for page in range(1, last_page + 1)]
        
        # 병렬로 페이지 요청 제출
        future_to_page = {executor.submit(fetch_single_page, url, page_num): page_num for url, page_num in page_urls}
        
        # 결과 수집
        for future in concurrent.futures.as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                page_minwons = future.result()
                if page_minwons:
                    all_minwons.extend(page_minwons)
                    print(f"페이지 {page_num}/{last_page}에서 {len(page_minwons)}개의 민원 정보를 추출했습니다.")
                else:
                    print(f"페이지 {page_num}/{last_page}에서 민원 정보를 추출하지 못했습니다.")
            except Exception as e:
                print(f"페이지 {page_num} 처리 중 오류 발생: {str(e)}")
    
    return all_minwons

def fetch_single_page(url, page_num):
    """단일 페이지의 민원 목록을 가져오는 함수"""
    session = get_session()
    try:
        # 재시도 로직 추가
        max_retries = 3
        for retry in range(max_retries):
            try:
                response = session.get(url, timeout=15)  # 타임아웃 15초로 증가
                if response.status_code == 200:
                    minwons = extract_minwon_list(response.text)
                    return minwons
                elif response.status_code == 429:  # Too Many Requests
                    print(f"페이지 {page_num} 요청 제한 (429). {retry+1}/{max_retries} 재시도 중...")
                    time.sleep(5 * (retry + 1))  # 점진적 대기 시간 증가
                    continue
                else:
                    print(f"페이지 {page_num} 데이터 요청 실패: 상태 코드 {response.status_code}")
                    return []
            except requests.exceptions.Timeout:
                print(f"페이지 {page_num} 요청 시간 초과. {retry+1}/{max_retries} 재시도 중...")
                time.sleep(3 * (retry + 1))
            except Exception as e:
                print(f"페이지 {page_num} 요청 중 오류: {str(e)}, {retry+1}/{max_retries} 재시도 중...")
                time.sleep(3)
                
        print(f"페이지 {page_num} 최대 재시도 횟수 초과.")
        return []
    except Exception as e:
        print(f"페이지 {page_num} 요청 중 치명적 오류: {str(e)}")
        return []

def clean_text(text):
    """텍스트 데이터 정제 함수"""
    if not text or not isinstance(text, str):
        return ""
    
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 연속된 공백 제거
    text = re.sub(r'\s+', ' ', text)
    
    # 특수문자 처리 (괄호 내용 유지, 나머지 특수문자는 공백으로)
    text = re.sub(r'[^\w\s\(\)\[\]\{\}가-힣]', ' ', text)
    
    # 불필요한 공백 정리
    text = text.strip()
    
    return text

def standardize_minwon_fields(minwon_data):
    """민원 데이터 필드 표준화 함수"""
    # 필드 표준화
    for field in minwon_data:
        if isinstance(minwon_data[field], str):
            minwon_data[field] = clean_text(minwon_data[field])
    
    # 처리 절차 표준화 - 단계 구분자 통일
    if '처리절차' in minwon_data and minwon_data['처리절차']:
        # 여러 구분자를 통일된 화살표로 변경
        proc = minwon_data['처리절차']
        
        # Float 값인 경우 string으로 변환
        if not isinstance(proc, str):
            proc = str(proc)
            
        proc = re.sub(r'[▶→⇒➡️⇨→▷▸▹▻►▼↓]+', '→', proc)
        proc = re.sub(r'[\s]*→[\s]*', ' → ', proc)
        minwon_data['처리절차'] = proc
    
    # 수수료 표준화
    if '수수료' in minwon_data and minwon_data['수수료']:
        fee = minwon_data['수수료']
        
        # Float 값인 경우 string으로 변환
        if not isinstance(fee, str):
            fee = str(fee)
            
        # '없음', '면제' 등의 표현 통일
        if re.search(r'없|무료|면제|면|0원|영|공|0', fee):
            minwon_data['수수료'] = '무료'
        # 금액 표기 방식 통일
        elif re.search(r'\d+', fee):
            # 숫자만 추출
            amounts = re.findall(r'\d+(?:,\d+)*(?:\.\d+)?', fee)
            if amounts:
                # 숫자가 있으면 "X원" 형식으로 통일
                minwon_data['수수료'] = f"{amounts[0]}원 ({fee})"
    
    # 처리기간 표준화
    if '처리기간' in minwon_data and minwon_data['처리기간']:
        period = minwon_data['처리기간']
        
        # Float 값인 경우 string으로 변환
        if not isinstance(period, str):
            period = str(period)
            
        # "즉시" 또는 "즉시처리" 등의 표현 통일
        if re.search(r'즉시|당일|실시간|바로', period):
            minwon_data['처리기간'] = '즉시처리'
        # "X일", "X시간" 등의 표현에서 숫자 추출
        else:
            days = re.search(r'(\d+)(?:\s*)(?:일|영업일|근무일)', period)
            hours = re.search(r'(\d+)(?:\s*)(?:시간)', period)
            minutes = re.search(r'(\d+)(?:\s*)(?:분)', period)
            
            if days:
                minwon_data['처리기간_일수'] = int(days.group(1))
            if hours:
                minwon_data['처리기간_시간'] = int(hours.group(1))
            if minutes:
                minwon_data['처리기간_분'] = int(minutes.group(1))
    
    return minwon_data

def add_metadata(minwon_data):
    """민원 데이터에 메타데이터 추가"""
    # 단어 수 계산
    if '설명' in minwon_data and minwon_data['설명']:
        minwon_data['설명_단어수'] = len(minwon_data['설명'].split())
    
    # 해시 ID 생성 (중복 감지용)
    hash_text = f"{minwon_data.get('민원명', '')}_{minwon_data.get('담당부서', '')}"
    minwon_data['hash_id'] = hashlib.md5(hash_text.encode()).hexdigest()
    
    # 복잡도 점수 산정 (필요한 필드 개수 기준)
    detail_fields = ['처리절차', '신청방법', '필요서류', '수수료', '담당기관', '연락처', '처리기간', '신청자격', '관련법령']
    filled_fields = sum(1 for field in detail_fields if field in minwon_data and minwon_data[field])
    minwon_data['상세정보_충실도'] = filled_fields / len(detail_fields)
    
    # 상세정보 유무에 따른 신뢰도 점수 
    if minwon_data.get('오류여부', '') == '정상' and filled_fields >= 3:
        minwon_data['신뢰도'] = '높음'
    elif minwon_data.get('오류여부', '') == '정상' and filled_fields >= 1:
        minwon_data['신뢰도'] = '중간'
    else:
        minwon_data['신뢰도'] = '낮음'
    
    return minwon_data

def identify_duplicate_minwons(minwon_list, similarity_threshold=0.85):
    """유사한 민원 항목 식별"""
    duplicates = []
    
    # 이름으로 그룹화
    name_groups = {}
    for idx, minwon in enumerate(minwon_list):
        name = minwon.get('민원명', '').strip()
        if name:
            if name not in name_groups:
                name_groups[name] = []
            name_groups[name].append((idx, minwon))
    
    # 유사 이름 감지
    unique_names = list(name_groups.keys())
    
    for i in range(len(unique_names)):
        for j in range(i+1, len(unique_names)):
            name1 = unique_names[i]
            name2 = unique_names[j]
            
            # 문자열 유사도 계산
            similarity = difflib.SequenceMatcher(None, name1, name2).ratio()
            
            if (similarity > similarity_threshold):
                for idx1, minwon1 in name_groups[name1]:
                    for idx2, minwon2 in name_groups[name2]:
                        duplicates.append({
                            'idx1': idx1,
                            'idx2': idx2,
                            'name1': name1,
                            'name2': name2,
                            'similarity': similarity,
                            'dept1': minwon1.get('담당부서', ''),
                            'dept2': minwon2.get('담당부서', '')
                        })
    
    return duplicates

def enhance_minwon_data(minwon_list):
    """민원 데이터 전체적인 품질 개선"""
    # 필드 표준화 및 메타데이터 추가
    enhanced_list = []
    for minwon in minwon_list:
        enhanced_minwon = standardize_minwon_fields(minwon.copy())
        enhanced_minwon = add_metadata(enhanced_minwon)
        enhanced_list.append(enhanced_minwon)
    
    # 중복 항목 식별
    duplicates = identify_duplicate_minwons(enhanced_list)
    
    # 중복 민원 중 더 상세한 정보를 가진 민원 선택
    if duplicates:
        print(f"{len(duplicates)}개의 유사/중복 민원 항목이 발견되었습니다.")
        # 중복 처리 로직을 별도로 구현할 수 있음
    
    return enhanced_list, duplicates

def save_to_jsonl_for_finetuning(minwon_list, filename=None):
    """인공지능 파인튜닝용 JSONL 형식으로 저장"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"정부24_민원_파인튜닝_{timestamp}.jsonl"
    
    desktop_path = os.path.expanduser("~/Desktop/data")
    file_path = os.path.join(desktop_path, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for minwon in minwon_list:
            if minwon.get('신뢰도', '') != '낮음':  # 신뢰도가 낮은 데이터는 제외
                # 기본 민원 정보 템플릿
                prompt_text = f"'{minwon['민원명']}'에 대해 알려주세요."
                
                # 복잡한 질문 템플릿 (여러 필드 조합)
                if '신청방법' in minwon and minwon['신청방법']:
                    q1 = f"'{minwon['민원명']}' 민원은 어떻게 신청하나요?"
                    a1 = f"{minwon['민원명']}의 신청방법은 다음과 같습니다: {minwon['신청방법']}"
                    
                    finetuning_data = {
                        "messages": [
                            {"role": "user", "content": q1},
                            {"role": "assistant", "content": a1}
                        ]
                    }
                    f.write(json.dumps(finetuning_data, ensure_ascii=False) + '\n')
                
                # 필요 서류 질문
                if '필요서류' in minwon and minwon['필요서류']:
                    q2 = f"'{minwon['민원명']}' 신청에 필요한 서류가 뭐예요?"
                    a2 = f"{minwon['민원명']} 신청에 필요한 서류는 다음과 같습니다: {minwon['필요서류']}"
                    
                    finetuning_data = {
                        "messages": [
                            {"role": "user", "content": q2},
                            {"role": "assistant", "content": a2}
                        ]
                    }
                    f.write(json.dumps(finetuning_data, ensure_ascii=False) + '\n')
                
                # 처리 절차 질문
                if '처리절차' in minwon and minwon['처리절차']:
                    q3 = f"'{minwon['민원명']}' 처리 절차가 어떻게 되나요?"
                    a3 = f"{minwon['민원명']}의 처리 절차는 다음과 같습니다: {minwon['처리절차']}"
                    
                    finetuning_data = {
                        "messages": [
                            {"role": "user", "content": q3},
                            {"role": "assistant", "content": a3}
                        ]
                    }
                    f.write(json.dumps(finetuning_data, ensure_ascii=False) + '\n')
                
                # 종합 정보 질문 (더 많은 필드가 있는 경우)
                detailed_fields = ['신청방법', '필요서류', '처리기간', '수수료', '담당기관']
                if sum(1 for f in detailed_fields if f in minwon and minwon[f]) >= 3:
                    q4 = f"'{minwon['민원명']}' 민원에 관한 상세 정보를 알려주세요."
                    
                    a4_parts = [f"{minwon['민원명']}에 관한 상세 정보입니다:"]
                    if '설명' in minwon and minwon['설명']:
                        a4_parts.append(f"- 설명: {minwon['설명']}")
                    if '신청방법' in minwon and minwon['신청방법']:
                        a4_parts.append(f"- 신청방법: {minwon['신청방법']}")
                    if '필요서류' in minwon and minwon['필요서류']:
                        a4_parts.append(f"- 필요서류: {minwon['필요서류']}")
                    if '처리기간' in minwon and minwon['처리기간']:
                        a4_parts.append(f"- 처리기간: {minwon['처리기간']}")
                    if '수수료' in minwon and minwon['수수료']:
                        a4_parts.append(f"- 수수료: {minwon['수수료']}")
                    if '담당기관' in minwon and minwon['담당기관']:
                        a4_parts.append(f"- 담당기관: {minwon['담당기관']}")
                    if '연락처' in minwon and minwon['연락처']:
                        a4_parts.append(f"- 문의처: {minwon['연락처']}")
                    
                    a4 = "\n".join(a4_parts)
                    
                    finetuning_data = {
                        "messages": [
                            {"role": "user", "content": q4},
                            {"role": "assistant", "content": a4}
                        ]
                    }
                    f.write(json.dumps(finetuning_data, ensure_ascii=False) + '\n')
    
    print(f"파인튜닝용 JSONL 파일이 저장되었습니다: {file_path}")
    return file_path

def generate_data_quality_report(minwon_list, filename=None):
    """데이터 품질 보고서 생성"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"정부24_민원_품질보고서_{timestamp}.html"
    
    desktop_path = os.path.expanduser("~/Desktop/data")
    file_path = os.path.join(desktop_path, filename)
    
    # 데이터프레임 변환
    df = pd.DataFrame(minwon_list)
    
    # 품질 지표 계산
    total_count = len(df)
    complete_fields = {
        '민원명': df['민원명'].notna().sum(),
        '설명': df['설명'].notna().sum(),
        '처리절차': df['처리절차'].notna().sum() if '처리절차' in df else 0,
        '신청방법': df['신청방법'].notna().sum() if '신청방법' in df else 0,
        '필요서류': df['필요서류'].notna().sum() if '필요서류' in df else 0,
        '수수료': df['수수료'].notna().sum() if '수수료' in df else 0,
        '처리기간': df['처리기간'].notna().sum() if '처리기간' in df else 0
    }
    
    # 신뢰도 분포
    trust_dist = df['신뢰도'].value_counts() if '신뢰도' in df else {'낮음': 0, '중간': 0, '높음': 0}
    
    # 오류 유형 분포
    error_dist = df['오류여부'].value_counts() if '오류여부' in df else {'정상': 0}
    
    # HTML 보고서 생성
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>정부24 민원 데이터 품질 보고서</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #333; }}
            .section {{ margin-bottom: 30px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .progress-container {{ width: 100%; background-color: #f1f1f1; }}
            .progress-bar {{ height: 20px; background-color: #4CAF50; }}
        </style>
    </head>
    <body>
        <h1>정부24 민원 데이터 품질 보고서</h1>
        <p>생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="section">
            <h2>1. 개요</h2>
            <p>총 수집 민원 수: {total_count}개</p>
        </div>
        
        <div class="section">
            <h2>2. 필드별 완성도</h2>
            <table>
                <tr>
                    <th>필드명</th>
                    <th>완성된 데이터 수</th>
                    <th>완성도 (%)</th>
                    <th>시각화</th>
                </tr>
    """
    
    for field, count in complete_fields.items():
        percentage = (count / total_count) * 100 if total_count > 0 else 0
        html_content += f"""
                <tr>
                    <td>{field}</td>
                    <td>{count} / {total_count}</td>
                    <td>{percentage:.1f}%</td>
                    <td>
                        <div class="progress-container">
                            <div class="progress-bar" style="width:{percentage}%"></div>
                        </div>
                    </td>
                </tr>
        """
    
    html_content += """
            </table>
        </div>
        
        <div class="section">
            <h2>3. 신뢰도 분포</h2>
            <table>
                <tr>
                    <th>신뢰도</th>
                    <th>데이터 수</th>
                    <th>비율 (%)</th>
                </tr>
    """
    
    for level, count in trust_dist.items():
        percentage = (count / total_count) * 100 if total_count > 0 else 0
        html_content += f"""
                <tr>
                    <td>{level}</td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
        """
    
    html_content += """
            </table>
        </div>
        
        <div class="section">
            <h2>4. 오류 유형 분포</h2>
            <table>
                <tr>
                    <th>오류 유형</th>
                    <th>데이터 수</th>
                    <th>비율 (%)</th>
                </tr>
    """
    
    for error, count in error_dist.items():
        percentage = (count / total_count) * 100 if total_count > 0 else 0
        html_content += f"""
                <tr>
                    <td>{error}</td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
        """
    
    html_content += """
            </table>
        </div>
        
        <div class="section">
            <h2>5. 인공지능 학습 적합성</h2>
            <p>신뢰도 '중간' 이상의 데이터 수: {trust_medium_high}개 ({trust_medium_high_percent:.1f}%)</p>
            <p>파인튜닝에 권장되는 최소 데이터 수는 1,000개입니다.</p>
            <p>결론: {conclusion}</p>
        </div>
    </body>
    </html>
    """.format(
        trust_medium_high=trust_dist.get('중간', 0) + trust_dist.get('높음', 0),
        trust_medium_high_percent=((trust_dist.get('중간', 0) + trust_dist.get('높음', 0)) / total_count * 100) if total_count > 0 else 0,
        conclusion="충분한 양질의 데이터가 확보되었습니다. 파인튜닝을 진행하세요." 
                if (trust_dist.get('중간', 0) + trust_dist.get('높음', 0)) >= 1000 
                else "데이터 품질은 적합하나 양이 부족합니다. 더 많은 데이터를 수집하세요."
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"데이터 품질 보고서가 저장되었습니다: {file_path}")
    return file_path

def main():
    """메인 함수"""
    print("정부24 민원 수집 프로그램을 시작합니다. (병렬 처리 및 속도 최적화 버전)")
    print("=" * 70)
    
    # 병렬 처리 설정 - 사용자 시스템 환경에 맞게 조정
    cpu_count = os.cpu_count() or 4
    page_workers = min(8, cpu_count)  # 페이지 병렬 처리 워커 수
    detail_workers = min(20, cpu_count * 5)  # 상세 정보 병렬 처리 워커 수
    batch_size = 50  # 한 번에 처리할 민원 배치 크기
    
    print(f"시스템 설정: CPU {cpu_count}개, 페이지 워커 {page_workers}개, 상세정보 워커 {detail_workers}개")
    
    # 1. 모든 정부 부서 목록 가져오기
    departments = get_department_list()
    print(f"총 {len(departments)}개 부서를 찾았습니다.")
    
    # 2. 부서 선택 옵션 제공
    print("\n수집할 부서를 선택하세요:")
    print("1. 모든 부서 수집")
    print("2. 주요 부서만 수집 (상위 10개)")
    print("3. 특정 부서만 수집")
    
    choice = input("선택 (1/2/3): ")
    
    target_departments = []
    if choice == '1':
        target_departments = departments
    elif choice == '2':
        target_departments = departments[:10]  # 상위 10개 부서만
    elif choice == '3':
        # 부서 목록 출력
        for i, dept in enumerate(departments, 1):
            print(f"{i}. {dept['name']} ({dept.get('group', '')})")
        
        try:
            dept_indices = input("수집할 부서 번호를 쉼표로 구분하여 입력하세요: ")
            indices = [int(idx.strip()) - 1 for idx in dept_indices.split(',')]
            target_departments = [departments[idx] for idx in indices if 0 <= idx < len(departments)]
        except:
            print("잘못된 입력입니다. 상위 5개 부서만 수집합니다.")
            target_departments = departments[:5]
    else:
        print("잘못된 선택입니다. 상위 5개 부서만 수집합니다.")
        target_departments = departments[:5]
    
    print(f"\n{len(target_departments)}개 부서의 민원 정보를 수집합니다:")
    for dept in target_departments:
        print(f"- {dept['name']} ({dept['code']})")
    
    print("\n병렬 처리로 최대한 빠르게 데이터를 수집합니다. 외부 링크도 처리합니다.")
    
    # 4. 모든 선택된 부서의 민원 정보 수집
    all_minwon_data = []
    
    # 오류 통계 추적을 위한 변수
    error_counts = {
        "총 민원 수": 0,
        "정상 처리": 0,
        "오류 발생": 0,
        "외부링크_처리됨": 0,
        "요청오류": 0,
        "HTTP오류": 0,
        "기타오류": 0,
        "링크없음": 0
    }
    
    # 진행 상황 출력용 변수
    total_processed = 0
    start_time = time.time()
    
    for i, dept in enumerate(target_departments, 1):
        dept_code = dept['code']
        dept_name = dept['name']
        
        print(f"\n[{i}/{len(target_departments)}] {dept_name} 부서의 민원 정보 수집을 시작합니다.")
        
        # 부서별 URL 생성
        base_url = f"https://www.gov.kr/search/svcmidMw?DEPT_INC_CD={dept_code}&SVC_DIV=mid"
        
        try:
            # 첫 페이지 데이터 가져오기
            response = session.get(base_url, timeout=10)
            if response.status_code == 200:
                html_content = response.text
                
                # 마지막 페이지 번호 추출
                last_page = get_last_page_number(html_content)
                print(f"{dept_name} 웹사이트에서 첫 페이지 데이터를 가져왔습니다. 총 {last_page}개의 페이지가 확인되었습니다.")
                
                # 병렬로 모든 페이지의 민원 목록 가져오기
                dept_minwon_list = fetch_pages_parallel(base_url, last_page, page_workers)
                print(f"{dept_name} 부서에서 총 {len(dept_minwon_list)}개의 민원 기본 정보를 추출했습니다.")
                
                # 상세 정보 수집 - 배치 처리로 병렬화
                if dept_minwon_list:
                    print(f"\n{dept_name} 부서의 민원 상세 정보 수집을 시작합니다. (전체 {len(dept_minwon_list)}개)")
                    
                    # 배치 처리로 나누기
                    batches = [dept_minwon_list[i:i+batch_size] for i in range(0, len(dept_minwon_list), batch_size)]
                    
                    processed_minwons = []
                    for batch_idx, batch in enumerate(batches, 1):
                        print(f"배치 {batch_idx}/{len(batches)} 처리 중... ({len(batch)}개 민원)")
                        processed_batch = batch_process_minwons(batch, detail_workers)
                        processed_minwons.extend(processed_batch)
                        
                        # 오류 통계 업데이트
                        for minwon in processed_batch:
                            if "오류여부" in minwon:
                                error_status = minwon["오류여부"]
                                if error_status == "정상":
                                    error_counts["정상 처리"] += 1
                                else:
                                    error_counts["오류 발생"] += 1
                                    if error_status in error_counts:
                                        error_counts[error_status] += 1
                                    else:
                                        error_counts["기타오류"] += 1
                        
                        # 진행 상황 표시
                        total_processed += len(batch)
                        elapsed_time = time.time() - start_time
                        avg_time_per_item = elapsed_time / total_processed if total_processed > 0 else 0
                        print(f"처리 속도: {total_processed/elapsed_time:.2f}개/초, 평균 처리 시간: {avg_time_per_item:.3f}초/민원")
                    
                    # 처리된 결과로 업데이트
                    dept_minwon_list = processed_minwons
                
                # 부서별 데이터 저장
                dept_data = {
                    'dept_code': dept_code,
                    'dept_name': dept_name,
                    'minwons': dept_minwon_list
                }
                all_minwon_data.append(dept_data)
                
                # 부서별 CSV 파일 저장 (진행 상황 백업용)
                save_to_csv(dept_minwon_list, f"정부24_민원목록_{dept_name}_{dept_code}.csv")
                
                error_counts["총 민원 수"] += len(dept_minwon_list)
                print(f"{dept_name} 부서의 민원 정보 수집 완료. 총 {len(dept_minwon_list)}개 처리됨.")
                
            else:
                print(f"{dept_name} 부서 데이터를 가져오지 못했습니다. 상태 코드: {response.status_code}")
                continue
                
        except Exception as e:
            print(f"{dept_name} 부서 정보 수집 중 오류 발생: {str(e)}")
            continue
    
    # 5. 모든 부서의 데이터를 하나의 CSV 파일로 통합
    if all_minwon_data:
        # 품질 개선
        print("\n데이터 품질 향상 작업을 시작합니다...")
        
        # 모든 민원 데이터를 하나의 리스트로 합치기
        all_minwons = []
        for dept_data in all_minwon_data:
            all_minwons.extend(dept_data['minwons'])
        
        print(f"총 {len(all_minwons)}개 민원 데이터에 대해 품질 개선을 수행합니다.")
        
        # 데이터 품질 개선
        enhanced_minwons, duplicates = enhance_minwon_data(all_minwons)
        
        # 중복 민원 보고서 저장
        if duplicates:
            duplicate_file = os.path.join(os.path.expanduser("~/Desktop/data"), f"중복민원_보고서_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(duplicate_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['idx1', 'idx2', 'name1', 'name2', 'similarity', 'dept1', 'dept2'])
                writer.writeheader()
                for item in duplicates:
                    writer.writerow(item)
            print(f"중복 민원 보고서가 저장되었습니다: {duplicate_file}")
        
        # 개선된 데이터로 CSV 저장
        enhanced_csv = os.path.join(os.path.expanduser("~/Desktop/data"), f"정부24_민원목록_품질개선_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        
        # 필드 확장 (신규 메타데이터 필드 포함)
        fieldnames = [
            "민원명", "설명", "담당부서", "인증필요", "유형", "링크", "링크텍스트",
            "처리절차", "신청방법", "필요서류", "수수료", "담당기관", "연락처", 
            "처리기간", "신청자격", "관련법령", "첨부파일", "기타정보", "수집부서코드", "오류여부",
            "설명_단어수", "hash_id", "상세정보_충실도", "신뢰도"
        ]
        
        with open(enhanced_csv, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for minwon in enhanced_minwons:
                writer.writerow(minwon)
        
        print(f"품질 개선된 CSV 파일이 저장되었습니다: {enhanced_csv}")
        
        # 파인튜닝용 JSONL 파일 생성
        finetune_file = save_to_jsonl_for_finetuning(enhanced_minwons)
        
        # 데이터 품질 보고서 생성
        report_file = generate_data_quality_report(enhanced_minwons)
        
        # 통합 CSV 파일도 저장
        combined_file = save_to_combined_csv(all_minwon_data)
        
        # 전체 민원 수 계산
        total_minwons = len(enhanced_minwons)
        total_depts = len(all_minwon_data)
        
        print(f"\n크롤링 및 데이터 품질 개선 완료: {total_depts}개 부서에서 총 {total_minwons}개의 민원 정보를 수집했습니다.")
        print(f"통합 CSV 파일: {combined_file}")
        print(f"품질 개선 CSV 파일: {enhanced_csv}")
        print(f"파인튜닝용 JSONL 파일: {finetune_file}")
        print(f"데이터 품질 보고서: {report_file}")
        
        # 오류 로그 파일 생성
        create_error_log(all_minwon_data)
    else:
        print("\n수집된 민원 정보가 없습니다.")
    
    # 크롤링 완료 시간 및 통계
    total_time = time.time() - start_time
    hours, remainder = divmod(total_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print("\n=== 크롤링 완료 통계 ===")
    print(f"총 소요 시간: {int(hours)}시간 {int(minutes)}분 {seconds:.1f}초")
    print(f"총 처리 민원 수: {error_counts['총 민원 수']}개")
    print(f"정상 처리: {error_counts['정상 처리']}개 ({error_counts['정상 처리']/max(1, error_counts['총 민원 수'])*100:.1f}%)")
    print(f"오류 발생: {error_counts['오류 발생']}개 ({error_counts['오류 발생']/max(1, error_counts['총 민원 수'])*100:.1f}%)")
    
    print("\n인공지능 학습 데이터 구축 완료! 파인튜닝을 시작하세요.")

def create_error_log(all_minwon_data, filename=None):
    """오류가 발생한 민원만 별도의 로그 파일로 저장하는 함수"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"정부24_민원목록_오류_{timestamp}.csv"
    
    desktop_path = os.path.expanduser("~/Desktop/data")
    file_path = os.path.join(desktop_path, filename)
    
    # 필드명 목록 (더 많은 오류 정보 포함)
    fieldnames = [
        "민원명", "담당부서", "링크", "오류여부", "기타정보", "수집부서코드", 
        "서비스ID", "카테고리", "일련번호", "오류발생시간"
    ]
    
    error_minwons = []
    for dept_data in all_minwon_data:
        for minwon in dept_data['minwons']:
            if '오류여부' in minwon and minwon['오류여부'] != "정상":
                error_minwon = {
                    "민원명": minwon.get("민원명", ""),
                    "담당부서": minwon.get("담당부서", ""),
                    "링크": minwon.get("링크", ""),
                    "오류여부": minwon.get("오류여부", "오류 미상"),
                    "기타정보": minwon.get("기타정보", ""),
                    "수집부서코드": dept_data['dept_code'],
                    "서비스ID": minwon.get("서비스ID", ""),
                    "카테고리": minwon.get("카테고리", ""),
                    "일련번호": minwon.get("일련번호", ""),
                    "오류발생시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                error_minwons.append(error_minwon)
    
    if error_minwons:
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for minwon in error_minwons:
                writer.writerow(minwon)
        
        print(f"\n오류 발생 민원 목록이 저장되었습니다: {file_path}")
        print(f"총 {len(error_minwons)}개의 오류 민원이 기록되었습니다.")
    else:
        print("\n오류 발생 민원이 없습니다.")
    
    return file_path

def create_minwon_dataset(base_url, output_dir, dept_code=None, start_page=1, end_page=None, max_pages=5):
    """
    지정된 URL에서 민원 데이터셋을 생성하는 함수
    
    Args:
        base_url: 크롤링할 기본 URL
        output_dir: 데이터셋을 저장할 디렉토리
        dept_code: 부서 코드 (선택)
        start_page: 시작 페이지 (기본값 1)
        end_page: 종료 페이지 (지정하지 않으면 자동 감지)
        max_pages: 최대 페이지 수 (기본값 5, 너무 많은 페이지를 한 번에 크롤링하지 않도록)
    
    Returns:
        생성된 CSV 파일 경로
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 세션 생성
    session = get_session()
    
    try:
        # 첫 페이지 요청
        first_page_url = get_page_url(base_url, start_page)
        response = session.get(first_page_url, timeout=15)
        
        if response.status_code != 200:
            print(f"첫 페이지 요청 실패: 상태 코드 {response.status_code}")
            return None
        
        # 마지막 페이지 번호 추출
        if end_page is None:
            last_page = get_last_page_number(response.text)
            print(f"감지된 총 페이지 수: {last_page}")
            
            # 최대 페이지 수 제한
            if max_pages and last_page > start_page + max_pages - 1:
                last_page = start_page + max_pages - 1
                print(f"처리할 최대 페이지 수를 {max_pages}개로 제한합니다. (마지막 페이지: {last_page})")
        else:
            last_page = end_page
        
        # 첫 페이지의 민원 목록 추출
        first_page_minwons = extract_minwon_list(response.text)
        all_minwons = first_page_minwons
        
        print(f"첫 페이지에서 {len(first_page_minwons)}개의 민원 정보를 추출했습니다.")
        
        # 나머지 페이지 처리
        if last_page > start_page:
            remaining_pages = list(range(start_page + 1, last_page + 1))
            
            # 페이지 URLs 생성
            page_urls = [(get_page_url(base_url, page), page) for page in remaining_pages]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_page = {executor.submit(fetch_single_page, url, page_num): page_num 
                                 for url, page_num in page_urls}
                
                for future in concurrent.futures.as_completed(future_to_page):
                    page_num = future_to_page[future]
                    try:
                        page_minwons = future.result()
                        if page_minwons:
                            all_minwons.extend(page_minwons)
                            print(f"페이지 {page_num}/{last_page}에서 {len(page_minwons)}개의 민원 정보를 추출했습니다.")
                        else:
                            print(f"페이지 {page_num}/{last_page}에서 민원 정보를 추출하지 못했습니다.")
                    except Exception as e:
                        print(f"페이지 {page_num} 처리 중 오류 발생: {str(e)}")
        
        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dept_part = f"_{dept_code}" if dept_code else ""
        csv_filename = f"정부24_민원목록{dept_part}_p{start_page}-{last_page}_{timestamp}.csv"
        csv_path = os.path.join(output_dir, csv_filename)
        
        # 상세 정보를 포함한 필드명 목록
        fieldnames = [
            "민원명", "설명", "담당부서", "인증필요", "유형", "링크", "링크텍스트",
            "서비스ID", "카테고리", "일련번호", "상세페이지",
            "처리절차", "신청방법", "필요서류", "수수료", "담당기관", "연락처", 
            "처리기간", "신청자격", "관련법령", "첨부파일", "기타정보", "오류여부"
        ]
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for minwon in all_minwons:
                writer.writerow(minwon)
        
        print(f"CSV 파일이 저장되었습니다: {csv_path}")
        print(f"총 {len(all_minwons)}개의 민원 정보가 저장되었습니다.")
        
        return csv_path
        
    except Exception as e:
        print(f"데이터셋 생성 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def main_dataset_expansion():
    """민원 데이터셋 확장을 위한 메인 함수"""
    print("정부24 민원 데이터셋 확장 프로그램을 시작합니다.")
    print("=" * 70)
    
    desktop_path = os.path.expanduser("~/Desktop/data")
    output_dir = os.path.join(desktop_path, "정부24_민원데이터셋")
    os.makedirs(output_dir, exist_ok=True)
    
    # 기본 URL
    base_url = "https://www.gov.kr/search/applyMw"
    
    # 페이지 범위 설정 (예: 1부터 10페이지까지)
    start_page = 1
    max_pages_per_batch = 10  # 한 번에 처리할 최대 페이지 수
    
    # 첫 배치 처리
    print(f"\n배치 1: 페이지 {start_page}부터 {start_page + max_pages_per_batch - 1}까지 처리합니다.")
    csv_path = create_minwon_dataset(
        base_url=base_url,
        output_dir=output_dir,
        start_page=start_page,
        max_pages=max_pages_per_batch
    )
    
    if csv_path:
        print(f"첫 번째 배치 처리 완료: {csv_path}")
        
        # 사용자 입력으로 다음 배치 처리 여부 결정
        while True:
            user_input = input("\n다음 배치를 계속 처리하시겠습니까? (y/n): ").strip().lower()
            if user_input == 'y':
                start_page += max_pages_per_batch
                print(f"\n배치 {(start_page // max_pages_per_batch) + 1}: 페이지 {start_page}부터 {start_page + max_pages_per_batch - 1}까지 처리합니다.")
                csv_path = create_minwon_dataset(
                    base_url=base_url,
                    output_dir=output_dir,
                    start_page=start_page,
                    max_pages=max_pages_per_batch
                )
                if csv_path:
                    print(f"배치 처리 완료: {csv_path}")
                else:
                    print("배치 처리 실패. 프로그램을 종료합니다.")
                    break
            elif user_input == 'n':
                print("프로그램을 종료합니다.")
                break
            else:
                print("올바른 입력이 아닙니다. 'y' 또는 'n'을 입력해주세요.")
    else:
        print("첫 번째 배치 처리 실패. 프로그램을 종료합니다.")

if __name__ == "__main__":
    # 기존 main 함수 대신 데이터셋 확장 함수 호출
    main_dataset_expansion()
