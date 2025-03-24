import csv
from bs4 import BeautifulSoup
import requests
import os
import re
import time
import urllib.parse
import concurrent.futures
import threading
import logging
import html
import argparse
import sys  # sys 모듈 추가
import traceback
from html import unescape

# 로깅 설정
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 텍스트 분석 및 NLP 관련 변수 초기화
NLTK_AVAILABLE = False
OKT_AVAILABLE = False
okt = None
NLP_ENABLED = False

# 터미널 색상 코드
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    @staticmethod
    def colorize(text, color):
        return f"{color}{text}{Colors.ENDC}"
    
    @staticmethod
    def supports_color():
        """터미널이 색상을 지원하는지 확인"""
        plat = sys.platform
        supported_platform = plat != 'win32' or 'ANSICON' in os.environ
        is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        return supported_platform and is_a_tty

# 텍스트 분석을 위한 패키지 추가
try:
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    NLTK_AVAILABLE = True
    
    # 필요한 NLTK 데이터 다운로드
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)
        
    logger.info("NLTK 텍스트 분석 모듈이 로드되었습니다.")
except ImportError:
    NLTK_AVAILABLE = False
    logger.warning("NLTK가 설치되지 않았습니다. 텍스트 분석 기능이 제한됩니다. (pip install nltk)")

# 모듈 존재 확인 후 임포트
import importlib.util

# 텍스트 분석 기능 설정 함수 추가
def set_nlp_enabled(enabled=False):
    """텍스트 분석 기능 활성화 여부 설정"""
    global NLP_ENABLED
    NLP_ENABLED = enabled
    logger.info(f"텍스트 분석 기능: {'활성화' if NLP_ENABLED else '비활성화'}")
    return NLP_ENABLED

# Java 환경 변수 설정 함수 추가
def setup_java_env():
    """Java 환경 변수를 설정하고 JVM을 초기화하는 함수"""
    java_home = os.environ.get('JAVA_HOME')
    
    if not java_home:
        # JVM 경로 직접 찾기 시도
        possible_java_paths = [
            '/usr/lib/jvm/default-java',
            '/usr/lib/jvm/java-11-openjdk-amd64',
            '/usr/lib/jvm/java-8-openjdk-amd64',
            '/usr/lib/jvm/java-8-openjdk',
            '/usr/lib/jvm/java',
            '/Library/Java/JavaVirtualMachines/jdk1.8.0_301.jdk/Contents/Home',  # macOS
            '/usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home',  # macOS Homebrew
            os.path.expanduser('~/Library/Java/JavaVirtualMachines/corretto-1.8.0_352/Contents/Home'),  # macOS 사용자 설치
        ]
        
        # 추가 시스템 경로 확인
        try:
            # 리눅스 시스템에서 실제 JVM 위치 찾기
            if os.path.exists('/usr/lib/jvm'):
                jvm_dirs = [os.path.join('/usr/lib/jvm', d) for d in os.listdir('/usr/lib/jvm') 
                            if os.path.isdir(os.path.join('/usr/lib/jvm', d))]
                possible_java_paths.extend(jvm_dirs)
        except Exception:
            pass
        
        for path in possible_java_paths:
            if os.path.exists(path) and os.path.exists(os.path.join(path, 'bin', 'java')):
                os.environ['JAVA_HOME'] = path
                logger.info(f"JAVA_HOME 자동 설정: {path}")
                break
    
    # JDK 유효성 검사
    if java_home or os.environ.get('JAVA_HOME'):
        jdk_path = os.environ.get('JAVA_HOME')
        
        # 유효한 JDK 경로 확인
        if not os.path.exists(os.path.join(jdk_path, 'bin', 'java')):
            logger.warning(f"설정된 JAVA_HOME({jdk_path})이 유효하지 않습니다. 올바른 JDK 경로를 설정하세요.")
            return False
            
        # JNI 경로 설정 (JPype에 필요)
        libjvm_paths = [
            os.path.join(jdk_path, 'jre', 'lib', 'amd64', 'server', 'libjvm.so'),  # Linux JDK 8
            os.path.join(jdk_path, 'lib', 'server', 'libjvm.so'),                  # Linux JDK 11+
            os.path.join(jdk_path, 'jre', 'lib', 'server', 'libjvm.dylib'),        # macOS JDK 8
            os.path.join(jdk_path, 'lib', 'server', 'libjvm.dylib'),               # macOS JDK 11+
        ]
        
        for libjvm_path in libjvm_paths:
            if os.path.exists(libjvm_path):
                os.environ['LD_LIBRARY_PATH'] = os.path.dirname(libjvm_path)
                logger.info(f"JVM 라이브러리 경로 설정: {os.path.dirname(libjvm_path)}")
                break
                
        return True
    
    return False

if importlib.util.find_spec("konlpy") is not None:
    try:
        # JVM 환경 설정
        java_available = setup_java_env()
        
        if java_available:
            # JPype1 직접 초기화 시도
            try:
                import jpype1
                
                # JVM이 이미 시작되었는지 확인
                if not jpype1.isJVMStarted():
                    try:
                        jvm_path = jpype1.getDefaultJVMPath()
                        logger.info(f"기본 JVM 경로: {jvm_path}")
                        jpype1.startJVM(jvm_path, "-Dfile.encoding=UTF-8", convertStrings=True)
                        logger.info("JPype JVM 초기화 성공")
                    except Exception as jvm_e:
                        logger.error(f"JVM 시작 오류: {str(jvm_e)}")
                            
                            # 마지막 수단: 직접 경로 지정 시도
                            try:
                                if os.environ.get('JAVA_HOME'):
                                    alt_jvm_path = os.path.join(os.environ['JAVA_HOME'], 'lib', 'server', 'libjvm.so')
                                    if os.path.exists(alt_jvm_path):
                                        jpype1.startJVM(alt_jvm_path, "-Dfile.encoding=UTF-8", convertStrings=True)
                                        logger.info(f"대체 경로로 JVM 초기화 성공: {alt_jvm_path}")
                            except Exception as alt_jvm_e:
                                logger.error(f"대체 경로 JVM 시작 오류: {str(alt_jvm_e)}")
                    else:
                        logger.info("JVM이 이미 실행 중입니다.")
            except ImportError:
                logger.warning("JPype1 패키지가 설치되지 않았습니다. KoNLPy 기능이 제한됩니다.")
                logger.warning("설치 방법: pip install jpype1")
                raise
            except Exception as jpy_e:
                logger.warning(f"JPype 초기화 오류: {str(jpy_e)}")
            
            # KoNLPy 로드 시도
            try:
                konlpy_import = importlib.import_module("konlpy.tag")
                Okt = getattr(konlpy_import, "Okt")
                okt = Okt()
                OKT_AVAILABLE = True
                logger.info("KoNLPy Okt 한국어 분석기가 로드되었습니다.")
            except Exception as konlpy_e:
                logger.warning(f"KoNLPy 초기화 오류: {str(konlpy_e)}")
                logger.warning("KoNLPy는 설치되었지만 초기화에 실패했습니다.")
        else:
            logger.warning("Java(JDK)를 찾을 수 없습니다. KoNLPy 기능이 비활성화됩니다.")
    except Exception as e:
        logger.warning(f"KoNLPy 로드 중 오류 발생: {str(e)}. 한국어 분석 기능이 제한됩니다.")
        logger.info("해결 방법: Java(JDK 8 이상)를 설치하고 JAVA_HOME 환경변수를 설정하세요.")
        logger.info("예시: export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64")
        logger.info("자세한 내용은 'run.sh' 스크립트나 'java_setup.sh' 파일을 참조하세요.")
else:
    logger.warning("KoNLPy가 설치되지 않았습니다. 한국어 분석 기능이 제한됩니다. (pip install konlpy)")

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("tqdm이 설치되지 않았습니다. 진행 막대가 표시되지 않습니다. (pip install tqdm)")

# 로깅 설정 수정 (levelename -> levelname)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 스레드별 세션 관리
thread_local = threading.local()


subheading_to_field = {
    "지원형태": "기타정보",
    "지원내용": "기타정보",
    "지원대상": "신청자격",
    "절차/방법": "처리절차",
    "온라인신청": "신청방법",
    "접수기관": "담당기관",
    "근거법령": "관련법령",
    "소관기관": "담당기관",
    "최종수정일": "기타정보",
    "수수료": "수수료",
    "처리기간": "처리기간",
    "필요서류": "필요서류",
    # 추가 매핑
    "신청방법": "신청방법",
    "문의기관": "담당기관",
    "담당부서": "담당기관",
    "관련서식": "필요서류",
    # 추가 매핑 (정부24 HTML 구조 분석 결과)
    "처리부서": "담당기관",
    "신청대상": "신청자격",
    "신청기간": "신청기간",
    "제출서류": "필요서류",
    "구비서류": "필요서류",
    "첨부서류": "필요서류",
    "지원금액": "지원금액",
    "신청양식": "관련서식",
    "관할기관": "담당기관",
    "결제방법": "결제정보",
    "발급비용": "수수료",
    "수령방법": "수령방법",
    "처리상태": "처리상태",
    "민원유형": "민원유형",
    "서비스유형": "민원유형",
    "법적근거": "관련법령",
    "연락처": "연락처",
    "신청조건": "신청자격",
    "민원편람": "참고정보",
    "연관민원": "연관민원",
    "담당처": "담당기관",
    "접수처": "담당기관",
    "운영시간": "운영시간",
    "이용시간": "운영시간",
    "발급시간": "처리시간",
    "처리과정": "처리절차",
    "신청절차": "처리절차",
    "담당자": "담당자정보",
}

# 실패한 URL 저장 (재시도용)
failed_urls = set()
# 성공적으로 처리된 URL 캐시
successful_urls_cache = {}

def check_playwright_installed():
    """Playwright 설치 여부 확인 및 안내"""
    try:
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            return True
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                logger.error("Playwright 브라우저가 설치되지 않았습니다. 'playwright install' 명령을 실행하세요.")
            else:
                logger.error(f"Playwright 초기화 오류: {str(e)}")
            return False
    except ImportError:
        logger.error("Playwright가 설치되지 않았습니다. 'pip install playwright' 후 'playwright install'을 실행하세요.")
        return False

def clean_text(text):
    """HTML 엔터티를 디코딩하고 텍스트 정리"""
    if not text:
        return ""
    text = unescape(text.strip())
    text = re.sub(r'\s+', ' ', text)  # 연속된 공백 제거
    return text

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

# URL 처리 방식 캐싱 (속도 최적화)
url_processing_cache = {}

def get_page_content(url, max_retries=3):
    """URL의 페이지 콘텐츠를 BeautifulSoup 객체로 반환 (개선된 재시도 로직)"""
    global url_processing_cache, failed_urls, successful_urls_cache
    
    # 이미 성공적으로 처리된 URL이라면 캐시에서 반환
    if url in successful_urls_cache:
        logger.info(f"캐시된 결과 사용: {url}")
        return successful_urls_cache[url]
    
    # 캐싱된 URL 처리 방식 확인 (속도 최적화)
    if url in url_processing_cache:
        method = url_processing_cache[url]
        if method == "requests":
            try:
                session = get_session()
                response = session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 유효한 페이지인지 확인 (최소한의 내용 검증)
                if "민원" in soup.text or "서비스" in soup.text:
                    logger.info(f"캐시된 방식(requests)으로 URL 처리: {url}")
                    successful_urls_cache[url] = soup  # 성공 결과 캐싱
                    return soup
                
                logger.warning(f"캐시된 방식(requests)의 응답이 유효하지 않음: {url}")
                url_processing_cache.pop(url, None)  # 캐시 무효화
            except:
                logger.warning(f"캐시된 방식(requests)이 실패, 재확인: {url}")
                url_processing_cache.pop(url, None)
        elif method == "playwright":
            try:
                soup = get_content_with_playwright(url)
                if soup and ("민원" in soup.text or "서비스" in soup.text):
                    logger.info(f"캐시된 방식(playwright)으로 URL 처리: {url}")
                    successful_urls_cache[url] = soup  # 성공 결과 캐싱
                    return soup
                logger.warning(f"캐시된 방식(playwright)의 응답이 유효하지 않음: {url}")
                url_processing_cache.pop(url, None)  # 캐시 무효화
            except:
                logger.warning(f"캐시된 방식(playwright)이 실패, 재확인: {url}")
                url_processing_cache.pop(url, None)
    
    # 재시도 로직 강화
    for attempt in range(max_retries):
        # 요청 간 지수 백오프 (서버 부하 방지)
        if attempt > 0:
            sleep_time = min(2 ** attempt, 10)  # 최대 10초까지 대기
            logger.info(f"재시도 {attempt+1}/{max_retries}, {sleep_time}초 대기 후 다시 시도: {url}")
            time.sleep(sleep_time)
        
        try:
            start_time = time.time()
            session = get_session()
            response = session.get(url, timeout=15)
            response.raise_for_status()
            
            # JS 페이지 감지 개선
            js_indicators = [
                "document.getElementById",
                "$(document).ready",
                "<body onload=",
                "window.onload",
                "javascript:"
            ]
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 유효한 콘텐츠 확인 (최소 내용 검증)
            content_valid = "민원" in soup.text or "서비스" in soup.text
            
            needs_js = False
            for indicator in js_indicators:
                if indicator in response.text and ("<table" in response.text or "iframe" in response.text) and len(response.text) < 2000:
                    needs_js = True
                    break
                    
            if needs_js or not content_valid:
                logger.info(f"JS 기반 페이지 또는 유효하지 않은 내용 감지, Playwright 사용: {url}")
                url_processing_cache[url] = "playwright"
                soup = get_content_with_playwright(url)
                if soup:
                    successful_urls_cache[url] = soup  # 성공 결과 캐싱
                    return soup
            else:
                processing_time = time.time() - start_time
                logger.info(f"일반 요청으로 처리 완료: {url} (처리시간: {processing_time:.2f}초)")
                url_processing_cache[url] = "requests"
                successful_urls_cache[url] = soup  # 성공 결과 캐싱
                return soup
        except Exception as e:
            logger.warning(f"시도 {attempt+1}/{max_retries} 실패: {url}, 오류: {str(e)}")
            if attempt == max_retries - 1:
                failed_urls.add(url)  # 재시도 실패한 URL 기록
                logger.error(f"최대 재시도 횟수 초과, Playwright로 최종 시도: {url}")
                return get_content_with_playwright(url)
    
    # 모든 재시도 실패
    failed_urls.add(url)
    return None

def get_content_with_playwright(url, timeout=30000):
    """Playwright를 사용하여 페이지 콘텐츠를 BeautifulSoup 객체로 반환 (개선됨)"""
    try:
        # Playwright 임포트 실패 시 대체 처리
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright가 설치되지 않았습니다. pip install playwright 를 실행하세요.")
            return None

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={'width': 1366, 'height': 768},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
                )
                page = context.new_page()
                page.set_default_timeout(timeout)
                
                # 페이지 로딩 속성 설정
                page.goto(url, wait_until="domcontentloaded")
                
                # 추가 대기 - 콘텐츠가 로드될 때까지
                try:
                    page.wait_for_selector('h2, table, .cont-box, .list_info_txt', timeout=10000)
                except:
                    logger.warning(f"Playwright 선택자 대기 시간 초과: {url}")
                
                # 페이지 스크롤
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)  # 추가 컨텐츠 로드 대기
                
                html = page.content()
                browser.close()
                
                soup = BeautifulSoup(html, 'html.parser')
                if soup and len(soup.text) > 100:  # 최소한의 콘텐츠 확인
                    successful_urls_cache[url] = soup  # 성공 결과 캐싱
                    return soup
                else:
                    logger.error(f"Playwright로 가져온 HTML이 너무 짧거나 비어 있습니다: {url}")
                    return None
            except Exception as e:
                logger.error(f"Playwright 브라우저 실행 중 오류: {str(e)}")
                return None
    except Exception as e:
        logger.error(f"Playwright 처리 중 예외 발생: {str(e)}")
        return None

def extract_minwon_list(html_content):
    """정부24 웹페이지에서 민원 목록을 추출하는 함수 (개선됨)"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 대체 선택자 추가 및 세분화 (HTML 파일 분석 결과 반영)
    selectors = [
        'li.result_li_box',
        'li[class*="result"]',
        'div.result-list li',
        'ul.search-result-list li',
        'ul.service_list li',  # index1.html 기반 추가
        'li.in_bn',            # index1.html 기반 추가
        'div.service_apply_list_wrap li', # 서비스 목록 추가
        'div.unifiedSch_lst li' # 검색 결과 목록 추가
    ]
    
    minwon_items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            minwon_items = items
            logger.info(f"선택자 '{selector}'로 {len(items)}개 항목 발견")
            break
    
    if not minwon_items:
        logger.warning("어떤 선택자로도 민원 항목을 찾지 못했습니다.")
    
    minwon_list = []
    
    for item in minwon_items:
        try:
            # 제목 및 링크 추출 - HTML 구조 분석 기반 선택자 추가
            title_selectors = [
                'a.list_font17', 
                'a[class*="list_font"]', 
                'a.title', 
                'strong a', 
                'p.tit a',
                'h1', 'h2', 'h3',  
                'div.title', 'div.subject', 'div.service-name',
                'dt a',              # index1.html 기반 추가
                'dl dt a',           # index1.html 기반 추가
                'div.right_detail dt a', # index3.html 기반 추가
                'a[title]'           # 타이틀 속성이 있는 링크
            ]
            title_element = None
            for selector in title_selectors:
                title_element = item.select_one(selector)
                if title_element:
                    break
            
            if title_element:
                title = clean_text(title_element.text)
                link = title_element.get('href', '')
                if link and not link.startswith('http'):
                    link = urllib.parse.urljoin("https://www.gov.kr", link)
            else:
                # 제목이 없으면 다른 방식으로 시도
                title_tags = item.find_all(['strong', 'h3', 'h4', 'p'])
                for tag in title_tags:
                    if tag.text and len(tag.text.strip()) > 5:  # 최소 길이 확인
                        title = clean_text(tag.text)
                        link_tag = tag.find('a') or item.find('a')
                        link = link_tag.get('href', '') if link_tag else ""
                        if link and not link.startswith('http'):
                            link = urllib.parse.urljoin("https://www.gov.kr", link)
                        break
                else:
                    title = "제목 없음"
                    link = ""
                    logger.warning("민원명이 포함된 태그를 찾을 수 없습니다.")
            
            # 설명 추출 - 대체 선택자 추가
            desc_selectors = ['p.list_info_txt', 'div.desc', 'p.dec', 'div.summary', 'p.txt']
            desc_element = None
            for selector in desc_selectors:
                desc_element = item.select_one(selector)
                if desc_element:
                    break
            
            description = clean_text(desc_element.text) if desc_element else "설명 없음"
            
            # 부서 정보 추출 - 대체 선택자 추가
            dept_selectors = ['span.division_', 'span[class*="division"]', 'span.dept', 'div.department']
            dept_element = None
            for selector in dept_selectors:
                dept_element = item.select_one(selector)
                if dept_element:
                    break
            
            department = clean_text(dept_element.text) if dept_element else "부서 정보 없음"
            
            # 인증 정보 추출 - 대체 선택자 추가
            auth_selectors = ['span.confi_', 'span[class*="confi"]', 'span.auth', 'span.login-required']
            auth_element = None
            for selector in auth_selectors:
                auth_element = item.select_one(selector)
                if auth_element:
                    break
            
            auth_required = clean_text(auth_element.text) if auth_element else "정보 없음"
            
            # 유형 정보 추출 - 대체 선택자 추가
            badge_selectors = ['span.badge_gray', 'span[class*="badge"]', 'span.type', 'span.category']
            badge_element = None
            for selector in badge_selectors:
                badge_element = item.select_one(selector)
                if badge_element:
                    break
            
            badge = clean_text(badge_element.text) if badge_element else "유형 정보 없음"
            
            # 버튼 정보 추출 - 대체 선택자 추가
            button_selectors = ['a.small_btn', 'a[class*="btn"]', 'a.more', 'a.detail']
            button_element = None
            for selector in button_selectors:
                button_element = item.select_one(selector)
                if button_element:
                    break
            
            button_text = clean_text(button_element.text) if button_element else "버튼 없음"
            button_onclick = button_element.get('onclick', '') if button_element else ""
            
            capp_biz_cd, high_ctg_cd, tp_seq = "", "", ""
            if button_onclick:
                # 여러 패턴에 대응
                patterns = [
                    r"goUrlNewChk\('([^']+)',\s*'([^']+)',\s*'([^']+)'",
                    r"goServiceDetail\('([^']+)',\s*'([^']+)',\s*'([^']+)'",
                    r"fn_goServiceDetail\('([^']+)',\s*'([^']+)',\s*'([^']+)'",
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, button_onclick)
                    if match:
                        capp_biz_cd, high_ctg_cd, tp_seq = match.groups()
                        break
            
            # 카테고리 정보 추출 개선 (HTML 파일 분석 기반)
            category_selectors = [
                'span.kind_gray', 
                'span.category',
                'div.sorting_area span.doth',  # index1.html 기반 추가
                'div.kind span',               # 카테고리 정보
                'span[class*="category"]',     # 카테고리 클래스명 포함
                'div.service-category'         # 서비스 카테고리
            ]
            
            category_element = None
            for selector in category_selectors:
                category_element = item.select_one(selector)
                if category_element:
                    break
                    
            category = clean_text(category_element.text) if category_element else ""
            
            # 추가 메타데이터 추출 (HTML 파일 분석 기반)
            meta_info = {}
            
            # 처리기간 정보 추출
            processing_time_selectors = ['span.time', 'span.duration', 'p.processing-time']
            for selector in processing_time_selectors:
                element = item.select_one(selector)
                if element:
                    meta_info["처리기간"] = clean_text(element.text)
                    break
            
            # 수수료 정보 추출
            fee_selectors = ['span.fee', 'span.cost', 'p.fee-info']
            for selector in fee_selectors:
                element = item.select_one(selector)
                if element:
                    meta_info["수수료"] = clean_text(element.text)
                    break
                    
            # 민원 상태 정보 추출
            status_selectors = ['span.status', 'div.status', 'p.status-info']
            for selector in status_selectors:
                element = item.select_one(selector)
                if element:
                    meta_info["처리상태"] = clean_text(element.text)
                    break
            
            # 디테일 페이지 URL에서 민원 ID 추출 (개선됨)
            minwon_id = ""
            if link:
                id_match = re.search(r'serviceInfo/([A-Za-z0-9_]+)', link)
                if id_match:
                    minwon_id = id_match.group(1)
                else:
                    # 다른 형태의 ID 패턴 시도
                    alternate_match = re.search(r'[?&]id=([A-Za-z0-9_]+)', link)
                    if alternate_match:
                        minwon_id = alternate_match.group(1)
            
            # 기본 정보 및 확장 정보 병합
            minwon_data = {
                "민원명": title, 
                "설명": description, 
                "담당부서": department,
                "인증필요": auth_required, 
                "유형": badge, 
                "링크": link,
                "링크텍스트": button_text, 
                "서비스ID": capp_biz_cd or minwon_id,
                "카테고리": category or high_ctg_cd, 
                "일련번호": tp_seq, 
                "민원분류": badge,  # 민원/정부서비스 등 유형 정보
                "오류여부": "정상"
            }
            
            # 메타데이터 병합
            minwon_data.update(meta_info)
            
            minwon_list.append(minwon_data)
        except Exception as e:
            logger.error(f"민원 항목 처리 중 오류 발생: {str(e)}")
    
    logger.info(f"총 {len(minwon_list)}개의 민원 항목을 추출했습니다.")
    return minwon_list

def get_last_page_number(html_content):
    """HTML에서 마지막 페이지 번호를 추출하는 함수"""
    soup = BeautifulSoup(html_content, 'html.parser')
    try:
        pagination = soup.select_one('div.pagination_box')
        if pagination:
            last_page_link = pagination.select_one('li.page_last a')
            if last_page_link and 'onclick' in last_page_link.attrs:
                match = re.search(r"applySetPage\('(\d+\.?\d*)'\)", last_page_link['onclick'])
                if match:
                    return int(float(match.group(1)))
        return 1
    except Exception as e:
        logger.error(f"마지막 페이지 번호 추출 중 오류: {str(e)}")
        return 1

def get_page_url(base_url, page_number):
    """페이지 번호에 해당하는 URL을 생성하는 함수"""
    if '?' in base_url:
        if 'pageIndex=' in base_url:
            return re.sub(r'pageIndex=\d+', f'pageIndex={page_number}', base_url)
        return f"{base_url}&pageIndex={page_number}"
    return f"{base_url}?pageIndex={page_number}"

def save_to_csv(minwon_list, filename="정부24_민원목록.csv"):
    """민원 목록을 CSV 파일로 저장하는 함수 (개선된 필드 포함)"""
    desktop_path = os.path.expanduser("~/Desktop/data")
    os.makedirs(desktop_path, exist_ok=True)
    file_path = os.path.join(desktop_path, filename)
    
    # 필드 목록 확장 (HTML 분석 기반)
    fieldnames = [
        # 기본 필드
        "민원명", "설명", "담당부서", "인증필요", "유형", "링크", "링크텍스트",
        "서비스ID", "카테고리", "일련번호", "처리절차", "신청방법", "필요서류",
        "수수료", "담당기관", "연락처", "처리기간", "신청자격", "관련법령",
        "첨부파일", "기타정보", "오류여부",
        
        # 추가 필드
        "신청기간", "결제정보", "수령방법", "처리상태", "민원유형",
        "참고정보", "연관민원", "운영시간", "처리시간", "지원금액",
        "관련서식", "담당자정보", "서비스상태", "신청경로", "서비스분류",
        "민원분류", "프로세스이미지", "API정보"
    ]
    
    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for minwon in minwon_list:
            writer.writerow({k: minwon.get(k, "") for k in fieldnames})
    
    logger.info(f"CSV 파일이 저장되었습니다: {file_path}")
    return file_path

# 텍스트 분석 함수 및 설정 관련 변수
NLP_ENABLED = False

# 텍스트 분석 기능 설정 함수 추가
def set_nlp_enabled(enabled=False):
    """텍스트 분석 기능 활성화 여부 설정"""
    global NLP_ENABLED
    NLP_ENABLED = enabled
    logger.info(f"텍스트 분석 기능: {'활성화' if NLP_ENABLED else '비활성화'}")
    return NLP_ENABLED

# 텍스트 분석 함수 추가
def analyze_text(text, lang='ko'):
    """텍스트 분석으로 중요 키워드와 품질 점수 추출"""
    # 텍스트 분석 기능이 비활성화된 경우 빈 결과 반환
    if not NLP_ENABLED:
        return [], 0
        
    if not text or len(text) < 5:
        return [], 0
    
    # 기본 텍스트 정제
    text = clean_text(text)
    
    # 한국어 텍스트 분석 (KoNLPy 사용)
    if lang == 'ko' and OKT_AVAILABLE:
        try:
            # 명사 추출
            nouns = okt.nouns(text)
            # 불용어 필터링 (간단한 한국어 불용어 목록)
            ko_stopwords = {'이', '그', '저', '것', '및', '등', '외', '관한', '통한', '위한', '중', '및'}
            keywords = [word for word in nouns if word not in ko_stopwords and len(word) > 1]
            
            # 품질 점수 계산 (명사 비율, 길이 등 고려)
            quality_score = min(len(keywords) / max(len(text.split()), 1) * 100, 100) if keywords else 0
            
            return keywords[:10], quality_score
        except Exception as e:
            logger.warning(f"한국어 텍스트 분석 중 오류: {str(e)}")
    
    # 영어 또는 KoNLPy 사용 불가 시 기본 분석
    if NLTK_AVAILABLE:
        try:
            # 토큰화
            tokens = word_tokenize(text.lower())
            # 불용어 제거
            eng_stopwords = set(stopwords.words('english')) if lang == 'en' else set()
            keywords = [word for word in tokens if word.isalnum() and word not in eng_stopwords and len(word) > 2]
            
            # 빈도 기반 중요 키워드 추출
            from collections import Counter
            keyword_freq = Counter(keywords)
            top_keywords = [word for word, _ in keyword_freq.most_common(10)]
            
            # 품질 점수
            quality_score = min(len(set(keywords)) / max(len(tokens), 1) * 100, 100) if keywords else 0
            
            return top_keywords, quality_score
        except Exception as e:
            logger.warning(f"NLTK 텍스트 분석 중 오류: {str(e)}")
    
    # 모든 분석 방법 실패 시 간단한 워드 카운팅
    words = [w for w in re.findall(r'\w+', text.lower()) if len(w) > 2]
    from collections import Counter
    word_counts = Counter(words)
    
    # 기본 품질 점수 - 텍스트 길이와 고유 단어 비율
    unique_ratio = len(set(words)) / max(len(words), 1)
    quality_score = min(unique_ratio * 50, 100)  # 최대 100점
    
    return [word for word, _ in word_counts.most_common(5)], quality_score

# enhance_text_with_keywords 함수 수정
def enhance_text_with_keywords(original_text, similar_texts=None):
    """키워드 분석을 통해 텍스트 품질 향상"""
    # 텍스트 분석 기능이 비활성화된 경우 원본 텍스트 반환
    if not NLP_ENABLED:
        return original_text
        
    if not original_text:
        return original_text
    
    # 키워드 추출
    keywords, quality = analyze_text(original_text)
    
    # 품질이 이미 좋으면 그대로 반환
    if quality > 70 or not keywords:
        return original_text
    
    # 유사 텍스트가 있으면 키워드 보강
    combined_keywords = set(keywords)
    if similar_texts:
        for text in similar_texts:
            if text and text != original_text:
                more_keywords, _ = analyze_text(text)
                combined_keywords.update(more_keywords)
    
    # 원본 텍스트가 너무 짧으면 키워드로 보강
    if len(original_text) < 20 and combined_keywords:
        enhanced = f"{original_text} ({', '.join(list(combined_keywords)[:5])})"
        return enhanced
    
    return original_text

def extract_detail_info(url):
    # 결과 딕셔너리 초기화 - 더 많은 필드 추가
    detail_info = {
        # 기존 필드
        "인증필요": "",
        "유형": "민원",
        "링크": url,
        "링크텍스트": "",
        "서비스ID": url.split('/')[-1],
        "카테고리": "",
        "일련번호": "",
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
        "오류여부": "정상",
        
        # 추가 필드 (HTML 분석 결과 기반)
        "신청기간": "",        # 신청 가능한 기간
        "결제정보": "",        # 결제 방법 상세
        "수령방법": "",        # 발급물 수령 방법
        "처리상태": "",        # 현재 민원 처리 상태
        "민원유형": "",        # 민원의 세부 유형
        "참고정보": "",        # 추가 참고 정보
        "연관민원": "",        # 관련된 다른 민원 정보
        "운영시간": "",        # 서비스 운영 시간
        "처리시간": "",        # 처리에 소요되는 시간
        "지원금액": "",        # 지원금 관련 정보
        "관련서식": "",        # 관련 서식/양식 정보
        "담당자정보": "",      # 담당자 상세 정보
        "서비스상태": "",      # 서비스 활성화 상태
        "신청경로": "",        # 신청 가능한 경로 (온라인/오프라인)
        "서비스분류": "",      # 서비스의 세부 분류
    }

    try:
        # 기존 requests.get() 대신 get_page_content() 사용
        soup = get_page_content(url)
        if soup is None:
            raise Exception("페이지 콘텐츠를 가져오지 못했습니다.")

        # 민원명 추출 시도 (페이지 제목 우선)
        title_found = False
        
        # 메인 제목 선택자 확장 - 다양한 형태의 제목 캡처
        title_selectors = [
            'h1.tit', 'h1.title', 'h1.main-title', 'h1', 
            'h2.tit', 'h2.title', 'h2.sub-tit', 'h2:first-of-type', 
            '.service-title', '.main-title', '.content-title',
            'title'  # HTML title 태그에서도 제목 추출 시도
        ]
        
        for selector in title_selectors:
            title_tag = soup.select_one(selector)
            if title_tag and title_tag.text.strip():
                title_text = clean_text(title_tag.text)
                
                # "발급", "열람", "신청" 등의 키워드가 포함된 경우 민원명으로 인식
                keywords = ["발급", "열람", "신청", "등록", "민원", "신고", "조회", "교부"]
                
                if any(keyword in title_text for keyword in keywords) or len(title_text) > 5:
                    detail_info["민원명"] = title_text
                    title_found = True
                    logger.info(f"페이지 제목에서 민원명 추출: {title_text}")
                    break
        
        # HTML title 태그에서 괄호 형식의 민원명 추출 시도
        if not title_found:
            title_tag = soup.find('title')
            if title_tag:
                title_text = clean_text(title_tag.text)
                # 괄호 안에 있는 텍스트 추출 - "제목 - 민원24" 또는 "제목(부제) | 민원24" 형식 처리
                patterns = [
                    r'^(.*?)\s*[-|]\s*민원24',  # "제목 - 민원24" 또는 "제목 | 민원24" 형식
                    r'^(.*?)\s*\|\s*정부24',    # "제목 | 정부24" 형식
                    r'^(.*?)\s*[-|]\s*.*?정부',  # "제목 - 다른내용 정부" 형식
                    r'(.*?)\(\s*(.*?)\s*\)'     # "제목(부제)" 형식
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, title_text)
                    if match:
                        extracted_title = match.group(1).strip()
                        if len(extracted_title) > 3:  # 최소 길이 검증
                            detail_info["민원명"] = extracted_title
                            title_found = True
                            logger.info(f"HTML title에서 민원명 추출: {extracted_title}")
                            break
        
        # 링크텍스트 (발급 버튼 텍스트) - 대체 선택자 추가
        button_selectors = [
            'span.ibtn.large.navy a', 
            'a.button', 
            'a.btn_navy', 
            'a.btn-apply',
            'a[class*="btn"][class*="large"]'
        ]
        
        apply_button = None
        for selector in button_selectors:
            apply_button = soup.select_one(selector)
            if apply_button:
                break
                
        if apply_button:
            detail_info["링크텍스트"] = clean_text(apply_button.text)

        # 인증 필요 여부 확인 (개선)
        login_indicators = ["로그인", "인증", "login", "authentication"]
        if apply_button:
            button_text = apply_button.text.lower() if apply_button.text else ""
            button_onclick = apply_button.get('onclick', '').lower()
            
            for indicator in login_indicators:
                if indicator in button_text or indicator in button_onclick:
                    detail_info["인증필요"] = "인증필요"
                    break

        # 섹션별 정보 추출 - 선택자 및 섹션 인식 개선
        section_selectors = [
            # 기존 선택자
            ('h2', lambda x: x and x.startswith('h2-ico')),
            ('h2', 'sub-tit'),
            ('h3', 'tit'),
            ('h3', lambda x: x and 'title' in x),
            
            # HTML 분석 기반 추가 선택자
            ('h2', 'guide_cont_title'),  # index4.html 기반
            ('h3', 'guide_cont_title'),
            ('dt', None),               # 정의 목록 제목
            ('th', None),               # 테이블 헤더
            ('p', 'as_tit'),            # 사이드바 제목 (index1.html)
            ('strong', None),           # 강조 텍스트 제목
            ('div', 'title_box_tab')    # 탭 제목 컨테이너 (index3.html)
        ]
        
        sections_found = False
        
        for tag, class_filter in section_selectors:
            h_tags = soup.find_all(tag, class_=class_filter)
            if h_tags:
                sections_found = True
                for h_tag in h_tags:
                    # 다음 형제 요소 중 콘텐츠 박스 찾기
                    siblings = list(h_tag.next_siblings)
                    cont_box = None
                    
                    for sibling in siblings:
                        if sibling.name in ['div', 'ul'] and ('cont-box' in sibling.get('class', []) or 'content' in sibling.get('class', [])):
                            cont_box = sibling
                            break
                    
                    if not cont_box:
                        # 다음 h2 태그 전까지의 모든 내용을 콘텐츠로 간주
                        cont_box = soup.new_tag('div')
                        for sibling in siblings:
                            if sibling.name == tag and sibling.get('class') == h_tag.get('class'):
                                break
                            if sibling.name:  # 텍스트 노드가 아닌 경우만
                                cont_box.append(sibling)
                    
                    if cont_box:
                        list_items = cont_box.find_all('li')
                        
                        if not list_items:  # li가 없으면 다른 구조 확인
                            list_items = cont_box.find_all(['p', 'div'], class_=['item', 'field', 'row'])
                        
                        for li in list_items:
                            # 항목 제목 찾기 (대체 선택자)
                            title_selectors = ['p.tt', 'strong', 'span.label', 'span.tit', 'dt']
                            subheading_tag = None
                            
                            for selector in title_selectors:
                                subheading_tag = li.select_one(selector)
                                if subheading_tag:
                                    break
                            
                            if subheading_tag:
                                subheading = clean_text(subheading_tag.text)
                                
                                # 내용 부분 찾기 (대체 선택자)
                                content_selectors = ['div.tx', 'span.text', 'dd', 'p:not(.tt)', 'div.desc']
                                content_div = None
                                
                                for selector in content_selectors:
                                    content_div = li.select_one(selector)
                                    if content_div:
                                        break
                                
                                if not content_div:  # 특정 선택자가 없으면 제목 이후의 모든 텍스트
                                    content_div = subheading_tag.find_next()
                                
                                if content_div:
                                    content = clean_text(content_div.get_text(separator=' '))

                                    # 특수 처리
                                    if subheading == "온라인신청":
                                        link = content_div.find('a')
                                        if link:
                                            content = link['href']
                                    elif subheading == "근거법령":
                                        laws = [clean_text(a.text) for a in content_div.find_all('a')]
                                        content = ', '.join(laws) if laws else content
                                    elif "접수기관" in subheading and "연락처" in content:
                                        parts = content.split("연락처")
                                        if len(parts) > 1:
                                            detail_info["연락처"] = clean_text(parts[1])
                                            content = clean_text(parts[0])
                                    elif "담당" in subheading and ":" in content:  # 담당자 및 연락처 분리
                                        parts = content.split(":")
                                        if len(parts) > 1 and (re.search(r'\d{2,3}-\d{3,4}-\d{4}', parts[1]) or 
                                                            "연락처" in parts[0].lower()):
                                            detail_info["연락처"] = clean_text(parts[1])
                                            content = clean_text(parts[0]) + " (연락처 별도 저장)"

                                    # 필드 매핑
                                    mapped = False
                                    for key, value in subheading_to_field.items():
                                        if key in subheading:
                                            field = value
                                            if field == "담당기관":
                                                detail_info[field] += content + " / "
                                            else:
                                                detail_info[field] = content
                                            mapped = True
                                            break
                                    
                                    if not mapped:
                                        detail_info["기타정보"] += f"{subheading}: {content} / "
        
        # 섹션 기반 접근이 실패한 경우 전체 페이지에서 유용한 정보 추출 시도
        if not sections_found or not title_found or not detail_info.get("처리절차") or not detail_info.get("신청방법"):
            logger.warning(f"구조화된 섹션이나 필수 정보를 찾지 못했습니다. 대체 추출 방법 시도: {url}")
            
            # 텍스트 분석으로 페이지 컨텐츠에서 중요 정보 발견 시도
            if NLP_ENABLED and (OKT_AVAILABLE or NLTK_AVAILABLE):
                # 페이지 전체 텍스트
                full_text = soup.get_text(separator=' ', strip=True)
                
                # 키워드 추출 및 문맥 분석
                keywords, _ = analyze_text(full_text)
                logger.info(f"페이지에서 추출한 주요 키워드: {', '.join(keywords)}")
                
                # 민원 관련 섹션 발견 시도 - 키워드 주변 문맥 분석
                procedure_patterns = ["신청", "방법", "절차", "순서", "단계", "접수"]
                docs_patterns = ["서류", "증명서", "구비", "필요", "지참"]
                
                # 처리절차가 누락된 경우 키워드 기반 텍스트 추출
                if not detail_info.get("처리절차"):
                    procedure_texts = []
                    for pattern in procedure_patterns:
                        if pattern in full_text:
                            for paragraph in soup.find_all(['p', 'div', 'li']):
                                if pattern in paragraph.text and len(paragraph.text.strip()) > 15:
                                    procedure_texts.append(clean_text(paragraph.text))
                    
                    if procedure_texts:
                        # 여러 텍스트 조각을 결합하여 처리 절차 구성
                        detail_info["처리절차"] = " → ".join(procedure_texts[:3])
                        logger.info(f"키워드 기반 처리절차 추출: {detail_info['처리절차'][:50]}...")
                
                # 필요서류 누락 시 관련 키워드로 검색
                if not detail_info.get("필요서류"):
                    docs_texts = []
                    for pattern in docs_patterns:
                        if pattern in full_text:
                            for paragraph in soup.find_all(['p', 'div', 'li']):
                                if pattern in paragraph.text and len(paragraph.text.strip()) > 10:
                                    docs_texts.append(clean_text(paragraph.text))
                    
                    if docs_texts:
                        detail_info["필요서류"] = " / ".join(docs_texts[:2])
                        logger.info(f"키워드 기반 필요서류 추출: {detail_info['필요서류'][:50]}...")
            
            # 제목 추출 강화 - 다양한 패턴 처리
            if not title_found:
                # 서비스명이나 민원명이 있는 일반적인 위치 확인
                service_title_patterns = [
                    # 표에서 제목/값 형태로 된 정보 찾기
                    {"row_header": ["서비스명", "민원명", "서비스 이름", "업무명"], "selector": "th"},
                    # 특정 클래스나 ID를 가진 요소 찾기
                    {"selector": "[class*='title'], [class*='subject'], [id*='title'], .serviceTitle, .minwonTitle"},
                    # 특정 텍스트 패턴이 있는 strong, b, div 요소 찾기
                    {"text_pattern": ["발급", "열람", "신청", "등록"], "selector": "strong, b, div.name"}
                ]
                
                # 패턴별로 검색
                for pattern in service_title_patterns:
                    if "row_header" in pattern:
                        # 표에서 찾기
                        for header_text in pattern["row_header"]:
                            header_elem = soup.find(pattern["selector"], string=lambda s: s and header_text in s)
                            if header_elem:
                                # 다음 td 또는 형제 요소에서 값 찾기
                                value_elem = header_elem.find_next('td') or header_elem.find_next_sibling()
                                if value_elem and value_elem.text.strip():
                                    detail_info["민원명"] = clean_text(value_elem.text)
                                    title_found = True
                                    break
                    elif "selector" in pattern:
                        # 선택자로 직접 찾기
                        elems = soup.select(pattern["selector"])
                        for elem in elems:
                            if elem and elem.text.strip() and len(elem.text.strip()) > 5:
                                detail_info["민원명"] = clean_text(elem.text)
                                title_found = True
                                break
                    
                    if title_found:
                        break
                        
                    if "text_pattern" in pattern and "selector" in pattern:
                        # 텍스트 패턴이 있는 요소 찾기
                        elems = soup.select(pattern["selector"])
                        for elem in elems:
                            if elem and elem.text.strip():
                                for keyword in pattern["text_pattern"]:
                                    if keyword in elem.text:
                                        detail_info["민원명"] = clean_text(elem.text)
                                        title_found = True
                                        break
                            if title_found:
                                break
                    
                    if title_found:
                        break
            
            # 서비스ID나 URL에서 힌트 얻기 (마지막 수단)
            if not title_found and detail_info["서비스ID"]:
                service_id = detail_info["서비스ID"]
                # 서비스 ID에서 형태소 분석하여 민원명 조합 시도
                if re.match(r'^[A-Za-z0-9_]+$', service_id):
                    parts = re.findall(r'[A-Z][a-z]*|[a-z]+|\d+', service_id)
                    if parts and len(parts) >= 2:
                        # 영문 ID를 한글 관련 용어로 대체 (간단한 예시)
                        id_to_name = {
                            "Car": "자동차", "Auto": "자동차", "Vehicle": "차량",
                            "Reg": "등록", "Registration": "등록",
                            "Issue": "발급", "Cert": "증명서", "Certificate": "증명서",
                            "Copy": "등본", "Original": "원본", "Tax": "세금"
                        }
                        
                        name_parts = []
                        for part in parts:
                            if part in id_to_name:
                                name_parts.append(id_to_name[part])
                            elif len(part) > 1:  # 의미 있는 길이의 부분만 포함
                                name_parts.append(part)
                        
                        if name_parts:
                            detail_info["민원명"] = " ".join(name_parts) + " 관련 민원"
                            title_found = True
            
            # 여전히 제목을 찾지 못했을 경우 URL 경로에서 추출 시도
            if not title_found:
                url_path = url.split('/')[-1].replace('-', ' ').replace('_', ' ')
                if len(url_path) > 5 and not url_path.isdigit():  # 숫자만으로 된 ID가 아닌 경우
                    detail_info["민원명"] = f"민원: {url_path}"
            
            # 처리절차가 없는 경우 대체 추출 시도
            procedure_sections = soup.find_all(['div', 'section'], class_=lambda x: x and ('process' in x or 'step' in x or 'procedure' in x))
            
            for section in procedure_sections:
                steps = section.find_all(['li', 'div'], class_=lambda x: x and ('step' in str(x).lower() or 'process' in str(x).lower()))
                
                if steps:
                    procedures = []
                    for step in steps:
                        procedures.append(clean_text(step.text))
                    
                    if procedures:
                        detail_info["처리절차"] = " → ".join(procedures)
                        break
        
        # 페이지에서 추가 정보 추출
        if not detail_info["신청방법"]:
            apply_info = soup.find(string=lambda text: text and "신청방법" in text)
            if apply_info:
                parent = apply_info.parent
                next_el = parent.find_next()
                if next_el:
                    detail_info["신청방법"] = clean_text(next_el.text)
        
        # 담당기관 정보 정리
        if detail_info["담당기관"].endswith(" / "):
            detail_info["담당기관"] = detail_info["담당기관"][:-3]  # 마지막 구분자 제거
        
        if detail_info["기타정보"].endswith(" / "):
            detail_info["기타정보"] = detail_info["기타정보"][:-3]  # 마지막 구분자 제거

        # 필수 정보 체크 및 오류 표시
        required_fields = ["처리절차", "신청방법"]
        missing_fields = [field for field in required_fields if not detail_info[field]]
        
        if missing_fields:
            logger.warning(f"필수 필드 누락: {', '.join(missing_fields)} - URL: {url}")
            
            # 최소한의 기본값 설정으로 오류 방지
            for field in missing_fields:
                detail_info[field] = f"정보 없음 (자동 생성)"
            
            detail_info["오류여부"] = "일부 정보 누락"

        # 최종 텍스트 품질 개선
        if NLP_ENABLED and OKT_AVAILABLE:
            # 유사 필드 간 텍스트 품질 향상
            if detail_info.get("처리절차") and detail_info.get("신청방법"):
                similar_texts = [detail_info.get("처리절차"), detail_info.get("신청방법")]
                detail_info["처리절차"] = enhance_text_with_keywords(detail_info["처리절차"], similar_texts)
                detail_info["신청방법"] = enhance_text_with_keywords(detail_info["신청방법"], similar_texts)
            
            # 필요서류 텍스트 품질 향상
            if detail_info.get("필요서류"):
                detail_info["필요서류"] = enhance_text_with_keywords(detail_info["필요서류"])

        # 추가 정보 추출 개선 - 구조화된 테이블에서 정보 추출
        tables = soup.find_all('table')
        for table in tables:
            # 테이블 제목 확인
            table_caption = table.find('caption')
            table_title = clean_text(table_caption.text) if table_caption else "정보 테이블"
            
            # 테이블 행 순회
            rows = table.find_all('tr')
            for row in rows:
                # 헤더와 데이터 셀 추출
                header_cell = row.find('th') or row.find('td', class_=lambda x: x and ('header' in x or 'title' in x or 'label' in x))
                if not header_cell:
                    continue
                    
                # 값 셀 찾기 (th 다음 요소 or td)
                value_cells = row.find_all('td')
                if not value_cells or len(value_cells) < (2 if header_cell.name == 'td' else 1):
                    continue
                    
                value_cell = value_cells[0] if header_cell.name == 'th' else value_cells[1]
                
                header_text = clean_text(header_cell.text)
                value_text = clean_text(value_cell.text)
                
                # 필드 매핑 및 데이터 저장
                mapped = False
                for key, field in subheading_to_field.items():
                    if key in header_text:
                        if field == "담당기관" and detail_info[field]:
                            detail_info[field] += " / " + value_text
                        else:
                            detail_info[field] = value_text
                        mapped = True
                        break
                        
                if not mapped and value_text:
                    detail_info["기타정보"] += f"{header_text}: {value_text} / "
        
        # 첨부파일 링크 추출 개선
        attachment_links = []
        file_selectors = [
            'a[href$=".pdf"]', 'a[href$=".hwp"]', 'a[href$=".doc"]', 'a[href$=".docx"]', 
            'a[href$=".xls"]', 'a[href$=".xlsx"]', 'a[href$=".zip"]', 'a[href$=".txt"]',
            'a.file', 'a[class*="download"]', 'a[class*="attach"]',
            'a[onclick*="download"]'
        ]
        
        for selector in file_selectors:
            attachments = soup.select(selector)
            for attachment in attachments:
                file_name = clean_text(attachment.text) or "첨부파일"
                file_link = attachment.get('href', '')
                if file_link and not file_link.startswith(('http://', 'https://')):
                    file_link = urllib.parse.urljoin(url, file_link)
                
                if file_link:
                    attachment_links.append(f"{file_name}: {file_link}")
        
        if attachment_links:
            detail_info["첨부파일"] = " | ".join(attachment_links)
        
        # 관련 서식 다운로드 링크 추출
        form_links = []
        form_selectors = [
            'a[href*="form"]', 'a[href*="template"]', 'a[onclick*="form"]',
            'a[title*="서식"]', 'a[title*="양식"]', 'a[class*="form"]',
            'a:contains("서식")', 'a:contains("양식")', 'a:contains("다운로드")'
        ]
        
        for selector in form_selectors:
            try:
                forms = soup.select(selector)
                for form in forms:
                    form_name = clean_text(form.text) or "서식 다운로드"
                    form_link = form.get('href', '')
                    if form_link and not form_link.startswith(('http://', 'https://')):
                        form_link = urllib.parse.urljoin(url, form_link)
                    
                    if form_link and not any(form_link in link for link in form_links) and not "javascript:void" in form_link:
                        form_links.append(f"{form_name}: {form_link}")
            except Exception as form_e:
                logger.warning(f"서식 추출 중 오류: {str(form_e)}")
        
        if form_links:
            detail_info["관련서식"] = " | ".join(form_links)
        
        # 프로세스 다이어그램/단계 이미지 추출
        process_images = []
        img_selectors = [
            'img[src*="process"]', 'img[src*="step"]', 'img[src*="procedure"]',
            'img[alt*="프로세스"]', 'img[alt*="절차"]', 'img[alt*="과정"]',
            'div.process img', 'div.step img', 'div.procedure img'
        ]
        
        for selector in img_selectors:
            images = soup.select(selector)
            for img in images:
                img_src = img.get('src', '')
                if img_src and not img_src.startswith(('http://', 'https://')):
                    img_src = urllib.parse.urljoin(url, img_src)
                
                if img_src:
                    process_images.append(img_src)
        
        if process_images:
            detail_info["프로세스이미지"] = " | ".join(process_images)
        
        # 처리 단계별 시간/소요일 추출 강화
        if not detail_info["처리기간"] or len(detail_info["처리기간"]) < 3:
            duration_patterns = [
                r'(\d+)[일|시간|분]',
                r'처리기간[은|:]?\s*(\d+)',
                r'(\d+)\s*(영업일|근무일|업무일)',
                r'(\d+)~(\d+)[일|시간|분]',
                r'최대\s*(\d+)[일|시간|분]',
                r'(\d+)일\s*이내'
            ]
            
            full_text = soup.get_text()
            for pattern in duration_patterns:
                matches = re.search(pattern, full_text)
                if matches:
                    detail_info["처리기간"] = clean_text(matches.group(0))
                    break
        
        # 오픈 API 또는 데이터 연계 정보 추출
        api_info = []
        api_sections = soup.find_all(['div', 'section'], class_=lambda x: x and ('api' in str(x).lower() or 'data' in str(x).lower()))
        for section in api_sections:
            api_info.append(clean_text(section.get_text(separator=' ', strip=True))[:200])
        
        if api_info:
            detail_info["API정보"] = " | ".join(api_info)
        
        # 서비스 상태 정보 추출
        status_selectors = [
            'span.status', 'div.status', 'p.status', 
            'span[class*="state"]', 'div[class*="state"]',
            'div.sorting_area span'  # index1.html 기반
        ]
        
        for selector in status_selectors:
            status_elements = soup.select(selector)
            status_texts = []
            
            for element in status_elements:
                text = clean_text(element.text)
                if text and len(text) < 20 and any(kw in text for kw in ["신청가능", "종료", "접수중", "서비스", "인증", "민원"]):
                    status_texts.append(text)
            
            if status_texts:
                detail_info["서비스상태"] = " / ".join(status_texts)
                break

        # 데이터 정리 및 중복 정보 제거
        # 담당기관 정보 정리
        if detail_info["담당기관"].endswith(" / "):
            detail_info["담당기관"] = detail_info["담당기관"][:-3]  # 마지막 구분자 제거
        
        if detail_info["기타정보"].endswith(" / "):
            detail_info["기타정보"] = detail_info["기타정보"][:-3]  # 마지막 구분자 제거

        return detail_info
    except Exception as e:
        logger.error(f"세부정보 추출 중 오류 발생: {str(e)}, URL: {url}")
        detail_info["오류여부"] = f"세부정보 추출 실패: {str(e)}"
        return detail_info

def fetch_single_page(url, page_num):
    """단일 페이지의 민원 목록을 가져오는 함수"""
    session = get_session()
    max_retries = 3
    for retry in range(max_retries):
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            minwon_list = extract_minwon_list(response.text)
            logger.info(f"페이지 {page_num}에서 {len(minwon_list)}개의 민원을 추출했습니다.")
            return minwon_list
        except requests.exceptions.RequestException as e:
            logger.warning(f"페이지 {page_num} 요청 실패, 재시도 {retry+1}/{max_retries}: {str(e)}")
            if retry == max_retries - 1:
                logger.error(f"페이지 {page_num} 요청 최종 실패: {str(e)}")
                return []
            time.sleep(2 * (retry + 1))
    return []

def fetch_pages_parallel(base_url, last_page, max_workers=5):
    """페이지 데이터를 병렬로 가져오는 함수"""
    all_minwons = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_single_page, get_page_url(base_url, page), page): page
            for page in range(1, last_page + 1)
        }
        for future in concurrent.futures.as_completed(futures):
            page_num = futures[future]
            try:
                page_minwons = future.result()
                all_minwons.extend(page_minwons)
                logger.info(f"페이지 {page_num}/{last_page}에서 {len(page_minwons)}개 민원 추출")
            except Exception as e:
                logger.error(f"페이지 {page_num} 처리 중 오류: {str(e)}")
    return all_minwons

# 데이터 유효성 검증 함수 추가
def validate_minwon_data(data):
    """민원 데이터의 필수 필드 유효성 검증 (개선됨)"""
    required_fields = ["민원명", "설명", "처리절차", "신청방법"]
    valid = True
    missing_fields = []
    
    for field in required_fields:
        value = data.get(field, "")
        if not value or value == "정보 없음" or len(value.strip()) < 2:  # 최소 길이 조건
            missing_fields.append(field)
            valid = False
    
    if not valid:
        logger.warning(f"유효하지 않은 데이터: {', '.join(missing_fields)} - 민원명: {data.get('민원명', '제목 없음')}")
        
        # 로컬 텍스트 분석으로 누락된 필드 보강 시도 - NLP 활성화 여부 확인
        if NLP_ENABLED and OKT_AVAILABLE and (data.get("설명") or data.get("민원명")):
            source_text = data.get("설명") or data.get("민원명")
            keywords, _ = analyze_text(source_text)
            
            if keywords and "민원명" in missing_fields and not data.get("민원명"):
                # 키워드에서 민원명 생성
                data["민원명"] = f"{' '.join(keywords[:3])} 관련 민원"
                missing_fields.remove("민원명")
                logger.info(f"텍스트 분석으로 민원명 생성: {data['민원명']}")
            
            if "설명" in missing_fields and data.get("민원명"):
                # 민원명에서 설명 생성
                data["설명"] = f"{data['민원명']}에 관한 민원 서비스입니다."
                missing_fields.remove("설명")
                logger.info(f"민원명에서 설명 생성: {data['설명']}")
        
        # 여전히 누락된 필드가 있으면 검증 실패
        if missing_fields:
            return False
    
    # 추가 데이터 품질 검사
    if data.get("민원명") == data.get("설명"):
        logger.warning(f"민원명과 설명이 동일함: {data.get('민원명')}")
        
        # 설명 개선 시도
        if NLP_ENABLED and OKT_AVAILABLE:
            keywords, _ = analyze_text(data.get("민원명"))
            if keywords:
                data["설명"] = f"{data['민원명']}은(는) {', '.join(keywords[:3])}와 관련된 민원입니다."
                logger.info(f"키워드로 설명 개선: {data['설명']}")
            else:
                return False
        else:
            return False
    
    return True

# 민원 정보 재크롤링 시도 함수
def retry_process_minwon(minwon, max_retries=3):
    """민원 데이터 유효성 검증 실패 시 재크롤링 시도 (개선됨)"""
    detail_url = minwon.get('링크')
    if not detail_url or detail_url == "링크 없음":
        minwon["오류여부"] = "링크없음"
        return minwon
        
    for retry in range(max_retries):
        logger.info(f"민원 '{minwon.get('민원명')}' 재처리 시도 {retry+1}/{max_retries}")
        if not detail_url.startswith('http'):
            detail_url = urllib.parse.urljoin("https://www.gov.kr", detail_url)
            
        # 캐시 무효화 후 재시도
        global url_processing_cache, successful_urls_cache
        if detail_url in url_processing_cache:
            del url_processing_cache[detail_url]
        
        if detail_url in successful_urls_cache:
            del successful_urls_cache[detail_url]
            
        # 재시도 간 지수 백오프
        wait_time = min(2 ** retry, 10)  # 최대 10초
        time.sleep(wait_time)
        
        # 다른 메서드 시도 (Playwright 강제 사용)
        if retry > 0:
            logger.info(f"재시도 {retry+1}: Playwright 강제 사용")
            soup = get_content_with_playwright(detail_url)
            if soup:
                # BeautifulSoup 객체에서 직접 정보 추출
                detail_info = extract_detail_info(detail_url)
                minwon.update(detail_info)
            else:
                logger.warning(f"Playwright로도 페이지를 가져오지 못했습니다: {detail_url}")
                continue
        else:
            detail_info = extract_detail_info(detail_url)
            minwon.update(detail_info)
        
        if validate_minwon_data(minwon):
            minwon["오류여부"] = "재처리 성공"
            return minwon
            
    # 최종 실패 - 최소한의 정보 채우기
    minwon["오류여부"] = "필수정보 누락"
    
    # 필수 필드에 기본값 설정
    required_fields = ["처리절차", "신청방법", "필요서류", "담당기관"]
    for field in required_fields:
        if not minwon.get(field):
            minwon[field] = "정보를 가져올 수 없음 (자동 생성)"
    
    return minwon

def save_checkpoint(minwon_list, filename="진행상황_checkpoint.csv"):
    """중간 작업 상태 저장"""
    try:
        logger.info(f"중간 작업 상태 저장 중... ({len(minwon_list)}개 항목)")
        save_to_csv(minwon_list, filename)
        logger.info(f"체크포인트 저장 완료: {filename}")
    except Exception as e:
        logger.error(f"체크포인트 저장 실패: {str(e)}")

def process_single_minwon(minwon):
    """단일 민원의 상세 정보를 처리하는 함수 (개선됨)"""
    detail_url = minwon.get('링크')
    if not detail_url or detail_url == "링크 없음":
        logger.warning(f"링크 없음: {minwon.get('민원명', '제목 없음')}")
        minwon["오류여부"] = "링크없음"
        return minwon
        
    try:
        if not detail_url.startswith('http'):
            detail_url = urllib.parse.urljoin("https://www.gov.kr", detail_url)
            
        logger.info(f"민원 처리 중: {minwon.get('민원명')} - {detail_url}")
        
        # 세부 정보 추출
        detail_info = extract_detail_info(detail_url)
        minwon.update(detail_info)
        
        # 데이터 유효성 검증 추가
        if not validate_minwon_data(minwon):
            logger.warning(f"유효성 검증 실패, 재시도: {minwon.get('민원명')}")
            return retry_process_minwon(minwon)
            
        # 성공 처리
        minwon["오류여부"] = "정상"
        return minwon
    except Exception as e:
        logger.error(f"민원 처리 중 예외 발생: {str(e)}, URL: {detail_url}")
        minwon["오류여부"] = f"처리 실패: {str(e)}"
        
        # 최소한의 정보 채우기
        required_fields = ["처리절차", "신청방법", "필요서류", "담당기관"]
        for field in required_fields:
            if not minwon.get(field):
                minwon[field] = "오류로 인해 정보를 가져올 수 없음"
        
        return minwon

def batch_process_minwons(minwon_batch, max_workers=None):
    """민원 목록의 상세 정보를 병렬로 처리하는 함수 (개선됨)"""
    if not minwon_batch:
        return []
        
    # 시스템 상태에 따라 워커 수 조정
    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, 5)  # 최대 5개로 제한 (서버 부하 방지)
    
    effective_workers = min(max_workers, len(minwon_batch))
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
        # 진행 상황 표시
        if TQDM_AVAILABLE:
            futures = {executor.submit(process_single_minwon, minwon): i for i, minwon in enumerate(minwon_batch)}
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="민원 처리"):
                try:
                    results.append(future.result())
                except Exception as e:
                    minwon = minwon_batch[futures[future]]
                    logger.error(f"민원 처리 실패: {minwon.get('민원명', '알 수 없음')}, 오류: {str(e)}")
                    minwon["오류여부"] = f"처리실패: {str(e)}"
                    results.append(minwon)
        else:
            # tqdm 없이 진행
            futures = {executor.submit(process_single_minwon, minwon): minwon for minwon in minwon_batch}
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    minwon = futures[future]
                    minwon["오류여부"] = f"처리실패: {str(e)}"
                    results.append(minwon)
                
                completed += 1
                if completed % 5 == 0:  # 5개마다 진행 상황 출력
                    logger.info(f"진행률: {completed}/{len(minwon_batch)} ({completed/len(minwon_batch)*100:.1f}%)")
    
    # 성공률 계산 및 표시
    success_count = sum(1 for m in results if "정상" in m.get("오류여부", "") or "성공" in m.get("오류여부", ""))
    success_rate = success_count / len(results) * 100 if results else 0
    logger.info(f"배치 처리 결과: 성공 {success_count}/{len(results)} ({success_rate:.1f}%)")
    
    return results

# 테스트 URL 함수 추가
def test_crawling(urls=None):
    """특정 URL에 대한 크롤링 테스트 실행"""
    if urls is None:
        # 기본 테스트 URL 목록
        urls = [
            "https://www.gov.kr/portal/service/serviceInfo/PTR000050100",  # 일반 페이지
            "https://www.gov.kr/portal/service/serviceInfo/174100000001"    # 복잡한 구조 페이지 (예시)
        ]
    
    logger.info("크롤링 테스트 시작...")
    results = []
    
    for url in urls:
        logger.info(f"테스트 URL 처리: {url}")
        try:
            start_time = time.time()
            detail_info = extract_detail_info(url)
            processing_time = time.time() - start_time
            
            success = validate_minwon_data(detail_info)
            status = "성공" if success else "일부 데이터 누락"
            
            logger.info(f"테스트 결과: {status}, 처리시간: {processing_time:.2f}초, URL: {url}")
            detail_info["처리시간"] = f"{processing_time:.2f}초"
            detail_info["처리상태"] = status
            results.append(detail_info)
        except Exception as e:
            logger.error(f"테스트 실패: {str(e)}, URL: {url}")
            results.append({
                "링크": url,
                "처리상태": "실패",
                "오류여부": str(e)
            })
    
    # 테스트 결과 저장
    save_to_csv(results, "테스트결과.csv")
    logger.info(f"테스트 완료: 총 {len(results)}개 URL 처리됨")
    return results

# 터미널 색상 코드
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    @staticmethod
    def colorize(text, color):
        return f"{color}{text}{Colors.ENDC}"
    
    @staticmethod
    def supports_color():
        """터미널이 색상을 지원하는지 확인"""
        plat = sys.platform
        supported_platform = plat != 'win32' or 'ANSICON' in os.environ
        is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        return supported_platform and is_a_tty

# CLI 대화형 인터페이스 클래스
class InteractiveCLI:
    def __init__(self):
        self.use_colors = Colors.supports_color()
        self.options = {
            "mode": "full",       # 크롤링 모드: full, page, test, url
            "page": 0,            # 특정 페이지 번호
            "output": os.path.expanduser("~/Desktop/data"),  # 출력 경로
            "workers": 0,         # 워커 수 (0=자동)
            "nlp": False,         # 텍스트 분석 사용 여부
            "url": "",            # 특정 URL (mode=url일 때 사용)
            "batch_size": 30      # 배치 크기
        }
    
    def colorize(self, text, color):
        """색상 지원 여부에 따라 텍스트 색상 적용"""
        if self.use_colors:
            return Colors.colorize(text, color)
        return text
    
    def print_header(self):
        """프로그램 헤더 출력"""
        header = """
┌─────────────────────────────────────────────┐
│            정부24 민원 수집 프로그램           │
└─────────────────────────────────────────────┘
        """
        print(self.colorize(header, Colors.HEADER + Colors.BOLD))
    
    def print_menu(self):
        """메인 메뉴 출력"""
        menu = """
[1] 크롤링 모드 선택
[2] 출력 경로 설정
[3] 병렬 처리 설정
[4] 텍스트 분석 설정
[5] 배치 크기 설정
[6] 현재 설정 확인
[7] 크롤링 시작
[8] 도움말
[0] 종료
"""
        print(self.colorize("메인 메뉴:", Colors.BLUE + Colors.BOLD))
        print(menu)
    
    def print_current_settings(self):
        """현재 설정 출력"""
        mode_desc = {
            "full": "전체 페이지 크롤링",
            "page": f"특정 페이지만 크롤링 (페이지: {self.options['page']})",
            "test": "테스트 모드 (샘플 URL만 처리)",
            "url": f"특정 URL만 처리 ({self.options['url']})"
        }
        
        nlp_status = "활성화" if self.options["nlp"] else "비활성화"
        workers = "자동" if self.options["workers"] == 0 else str(self.options["workers"])
        
        settings = f"""
{self.colorize('현재 설정:', Colors.BLUE + Colors.BOLD)}
┌────────────────┬────────────────────────────────────────┐
│ 크롤링 모드     │ {mode_desc[self.options['mode']]}
│ 출력 경로       │ {self.options['output']}
│ 병렬 처리 워커  │ {workers}
│ 텍스트 분석     │ {nlp_status}
│ 배치 크기       │ {self.options['batch_size']}
└────────────────┴────────────────────────────────────────┘
"""
        print(settings)
    
    def select_crawl_mode(self):
        """크롤링 모드 선택 메뉴"""
        menu = """
[1] 전체 페이지 크롤링
[2] 특정 페이지만 크롤링
[3] 테스트 모드 (샘플 URL 테스트)
[4] 특정 URL만 처리
[0] 이전 메뉴로
"""
        print(self.colorize("크롤링 모드 선택:", Colors.BLUE + Colors.BOLD))
        print(menu)
        
        while True:
            choice = input(self.colorize("선택 (0-4): ", Colors.GREEN))
            if choice == '0':
                return
            elif choice == '1':
                self.options["mode"] = "full"
                print(self.colorize("✓ 전체 페이지 크롤링 모드로 설정되었습니다.", Colors.GREEN))
                return
            elif choice == '2':
                self.options["mode"] = "page"
                try:
                    page = int(input(self.colorize("크롤링할 페이지 번호: ", Colors.GREEN)))
                    if page <= 0:
                        print(self.colorize("✗ 페이지 번호는 양수여야 합니다.", Colors.FAIL))
                        continue
                    self.options["page"] = page
                    print(self.colorize(f"✓ 페이지 {page}만 크롤링하도록 설정되었습니다.", Colors.GREEN))
                    return
                except ValueError:
                    print(self.colorize("✗ 올바른 숫자를 입력하세요.", Colors.FAIL))
            elif choice == '3':
                self.options["mode"] = "test"
                print(self.colorize("✓ 테스트 모드로 설정되었습니다.", Colors.GREEN))
                return
            elif choice == '4':
                self.options["mode"] = "url"
                url = input(self.colorize("처리할 URL: ", Colors.GREEN))
                if url and (url.startswith('http://') or url.startswith('https://')):
                    self.options["url"] = url
                    print(self.colorize(f"✓ URL '{url}'을 처리하도록 설정되었습니다.", Colors.GREEN))
                    return
                else:
                    print(self.colorize("✗ 올바른 URL을 입력하세요. (http:// 또는 https://로 시작)", Colors.FAIL))
            else:
                print(self.colorize("✗ 올바른 옵션을 선택하세요.", Colors.FAIL))
    
    def set_output_path(self):
        """출력 경로 설정"""
        current = self.options["output"]
        print(self.colorize(f"현재 출력 경로: {current}", Colors.BLUE))
        path = input(self.colorize("새 출력 경로 (기본값 유지: 엔터): ", Colors.GREEN))
        
        if not path:
            print(self.colorize("✓ 기본 출력 경로를 유지합니다.", Colors.GREEN))
            return
            
        path = os.path.expanduser(path)
        try:
            os.makedirs(path, exist_ok=True)
            self.options["output"] = path
            print(self.colorize(f"✓ 출력 경로가 '{path}'로 설정되었습니다.", Colors.GREEN))
        except Exception as e:
            print(self.colorize(f"✗ 경로 설정 오류: {str(e)}", Colors.FAIL))
    
    def set_workers(self):
        """병렬 처리 워커 수 설정"""
        current = "자동" if self.options["workers"] == 0 else str(self.options["workers"])
        cpu_count = os.cpu_count() or 4
        print(self.colorize(f"현재 워커 설정: {current} (시스템 CPU 코어: {cpu_count}개)", Colors.BLUE))
        
        print(self.colorize("병렬 처리 워커 수를 설정합니다. (0 = 자동)", Colors.BLUE))
        print("워커 수가 많을수록 처리 속도가 빨라질 수 있지만, 시스템 부하와 네트워크 부하가 증가합니다.")
        
        while True:
            try:
                workers = input(self.colorize(f"워커 수 (0-{cpu_count*2}, 기본값 유지: 엔터): ", Colors.GREEN))
                if not workers:
                    print(self.colorize("✓ 기본 워커 설정을 유지합니다.", Colors.GREEN))
                    return
                
                workers = int(workers)
                if workers < 0:
                    print(self.colorize("✗ 워커 수는 0 이상이어야 합니다.", Colors.FAIL))
                    continue
                    
                if workers > cpu_count*3:
                    confirm = input(self.colorize(f"경고: 워커 수({workers})가 CPU 코어 수({cpu_count})의 3배를 초과합니다. 계속하시겠습니까? (y/n): ", Colors.WARNING))
                    if confirm.lower() != 'y':
                        continue
                
                self.options["workers"] = workers
                print(self.colorize(f"✓ 워커 수가 {workers}로 설정되었습니다.", Colors.GREEN))
                return
            except ValueError:
                print(self.colorize("✗ 올바른 숫자를 입력하세요.", Colors.FAIL))
    
    def set_nlp(self):
        """텍스트 분석 사용 설정"""
        current = "활성화" if self.options["nlp"] else "비활성화"
        print(self.colorize(f"현재 텍스트 분석 설정: {current}", Colors.BLUE))
        
        # 모듈 설치 상태 확인
        nltk_status = "설치됨" if 'NLTK_AVAILABLE' in globals() and NLTK_AVAILABLE else "설치되지 않음"
        konlpy_status = "설치됨" if 'OKT_AVAILABLE' in globals() and OKT_AVAILABLE else "설치되지 않음"
        
        print(self.colorize(f"NLTK 상태: {nltk_status}, KoNLPy 상태: {konlpy_status}", Colors.BLUE))
        print("텍스트 분석을 활성화하면 민원 데이터 품질을 향상시킬 수 있지만 처리 속도가 느려질 수 있습니다.")
        
        if not ('OKT_AVAILABLE' in globals() and OKT_AVAILABLE):
            print(self.colorize("⚠ 경고: KoNLPy가 제대로 설정되지 않았습니다.", Colors.WARNING))
            print(self.colorize("  Java(JDK 8 이상)가 필요합니다. JAVA_HOME 환경변수를 설정하세요.", Colors.WARNING))
            print(self.colorize("  예시: export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64", Colors.WARNING))
            print(self.colorize("  또는 'sudo apt install default-jdk' 명령으로 Java를 설치하세요.", Colors.WARNING))
            print(self.colorize("  자세한 내용은 'java_setup.sh' 파일을 참조하세요.", Colors.WARNING))
        
        while True:
            choice = input(self.colorize("텍스트 분석 사용 (y/n): ", Colors.GREEN))
            if choice.lower() in ['y', 'yes']:
                self.options["nlp"] = True
                # 전역 NLP 플래그 설정
                set_nlp_enabled(True)
                print(self.colorize("✓ 텍스트 분석이 활성화되었습니다.", Colors.GREEN))
                
                if not ('OKT_AVAILABLE' in globals() and OKT_AVAILABLE):
                    print(self.colorize("⚠ KoNLPy가 설치되지 않았거나 JVM을 찾지 못했습니다. 한국어 분석 기능이 제한됩니다.", Colors.WARNING))
                    print("필요한 패키지:")
                    print("1. konlpy 설치: pip install konlpy")
                    print("2. jpype1 설치: pip install jpype1")
                    print("3. Java 설치(Ubuntu): sudo apt install default-jdk")
                    print("4. JAVA_HOME 설정: export JAVA_HOME=/usr/lib/jvm/default-java")
                    print(self.colorize("설정 도움말: './java_setup.sh' 스크립트를 실행하세요.", Colors.BLUE))
                return
            elif choice.lower() in ['n', 'no']:
                self.options["nlp"] = False
                # 전역 NLP 플래그 설정
                set_nlp_enabled(False)
                print(self.colorize("✓ 텍스트 분석이 비활성화되었습니다.", Colors.GREEN))
                return
            else:
                print(self.colorize("✗ 'y' 또는 'n'을 입력하세요.", Colors.FAIL))
    
    def set_batch_size(self):
        """배치 크기 설정"""
        current = self.options["batch_size"]
        print(self.colorize(f"현재 배치 크기: {current}", Colors.BLUE))
        print("배치 크기는 한 번에 처리할 민원 항목 수입니다. 값이 클수록 처리 속도가 빨라질 수 있지만, 메모리 사용량이 증가합니다.")
        
        while True:
            try:
                size = input(self.colorize("배치 크기 (10-100, 기본값 유지: 엔터): ", Colors.GREEN))
                if not size:
                    print(self.colorize("✓ 기본 배치 크기를 유지합니다.", Colors.GREEN))
                    return
                
                size = int(size)
                if size < 5:
                    print(self.colorize("✗ 배치 크기는 최소 5 이상이어야 합니다.", Colors.FAIL))
                    continue
                elif size > 100:
                    confirm = input(self.colorize("경고: 배치 크기가 100을 초과하면 서버 부하가 증가할 수 있습니다. 계속하시겠습니까? (y/n): ", Colors.WARNING))
                    if confirm.lower() != 'y':
                        continue
                
                self.options["batch_size"] = size
                print(self.colorize(f"✓ 배치 크기가 {size}로 설정되었습니다.", Colors.GREEN))
                return
            except ValueError:
                print(self.colorize("✗ 올바른 숫자를 입력하세요.", Colors.FAIL))
    
    def show_help(self):
        """도움말 표시"""
        help_text = """
┌─────────────────────────────────────────────────────────────────┐
│                      정부24 민원 수집 도움말                        │
├─────────────────────────────────────────────────────────────────┤
│ 크롤링 모드:                                                      │
│  - 전체 페이지: 모든 민원 페이지를 수집합니다.                          │
│  - 특정 페이지: 지정한 페이지만 수집합니다.                             │
│  - 테스트 모드: 샘플 URL로 기능을 테스트합니다.                         │
│  - 특정 URL: 입력한 URL만 처리합니다.                                │
├─────────────────────────────────────────────────────────────────┤
│ 출력 경로:                                                        │
│  민원 데이터가 저장될 경로를 지정합니다.                                │
├─────────────────────────────────────────────────────────────────┤
│ 병렬 처리:                                                        │
│  동시에 처리할 작업 수를 조절합니다. 값이 클수록 빠르지만                   │ 
│  시스템 리소스와 네트워크 부하가 커집니다.                               │
├─────────────────────────────────────────────────────────────────┤
│ 텍스트 분석:                                                       │
│  KoNLPy와 NLTK를 사용하여 민원 텍스트의 품질을 개선합니다.                │
│  한국어 처리를 위해 KoNLPy 설치가 필요합니다.                           │
├─────────────────────────────────────────────────────────────────┤
│ 배치 크기:                                                        │
│  한 번에 처리할 민원 항목 수입니다. 값이 크면 메모리 사용량이               │
│  증가하지만 처리 속도가 빨라질 수 있습니다.                              │
└─────────────────────────────────────────────────────────────────┘

필요 패키지 설치:
  pip install -r requirements.txt
  
추가 요구사항:
  KoNLPy 사용 시: Java JDK 설치 필요
  Playwright 사용 시: playwright install 명령 실행 필요
"""
        print(self.colorize(help_text, Colors.BLUE))
        input(self.colorize("계속하려면 엔터를 누르세요...", Colors.GREEN))
    
    def run_crawler(self):
        """크롤러 실행"""
        print(self.colorize("\n크롤링을 시작합니다...", Colors.BLUE + Colors.BOLD))
        
        # 사용자 확인
        print(self.colorize("다음 설정으로 크롤링을 실행합니다:", Colors.BLUE))
        self.print_current_settings()
        
        confirm = input(self.colorize("계속하시겠습니까? (y/n): ", Colors.GREEN))
        if confirm.lower() not in ['y', 'yes']:
            print(self.colorize("크롤링이 취소되었습니다.", Colors.WARNING))
            return
        
        try:
            # CLI 옵션에 따라 크롤러 실행
            args = argparse.Namespace()
            args.output = self.options["output"]
            args.workers = self.options["workers"]
            args.nlp = self.options["nlp"]
            args.test = False
            args.batch_size = self.options["batch_size"]  # 배치 크기 설정 추가
            
            if self.options["mode"] == "test":
                print(self.colorize("테스트 모드로 실행합니다...", Colors.BLUE))
                args.test = True
                args.page = 0
                run_crawler_with_args(args)
            elif self.options["mode"] == "page":
                print(self.colorize(f"페이지 {self.options['page']}만 처리합니다...", Colors.BLUE))
                args.page = self.options["page"]
                run_crawler_with_args(args)
            elif self.options["mode"] == "url":
                print(self.colorize(f"URL '{self.options['url']}'만 처리합니다...", Colors.BLUE))
                args.page = 0
                # 특정 URL 처리 로직
                results = test_crawling([self.options["url"]])
                if results:
                    print(self.colorize("처리 완료! 결과가 저장되었습니다.", Colors.GREEN))
            else:  # full mode
                print(self.colorize("전체 페이지를 크롤링합니다...", Colors.BLUE))
                args.page = 0
                run_crawler_with_args(args)
                
        except KeyboardInterrupt:
            print(self.colorize("\n사용자에 의해 크롤링이 중단되었습니다.", Colors.WARNING))
        except Exception as e:
            print(self.colorize(f"\n크롤링 중 오류 발생: {str(e)}", Colors.FAIL))
            logger.error(f"크롤링 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

    def run(self):
        """대화형 CLI 메인 루프"""
        self.print_header()
        
        while True:
            self.print_menu()
            choice = input(self.colorize("메뉴 선택 (0-8): ", Colors.GREEN))
            
            if choice == '0':
                print(self.colorize("프로그램을 종료합니다.", Colors.BLUE))
                break
            elif choice == '1':
                self.select_crawl_mode()
            elif choice == '2':
                self.set_output_path()
            elif choice == '3':
                self.set_workers()
            elif choice == '4':
                self.set_nlp()
            elif choice == '5':
                self.set_batch_size()
            elif choice == '6':
                self.print_current_settings()
            elif choice == '7':
                self.run_crawler()
            elif choice == '8':
                self.show_help()
            else:
                print(self.colorize("✗ 올바른 메뉴를 선택하세요.", Colors.FAIL))

def run_crawler_with_args(args):
    """명령행 인자로 크롤러 실행"""
    # 출력 디렉토리 설정
    output_dir = os.path.expanduser(args.output)
    os.makedirs(output_dir, exist_ok=True)
    
    # Playwright 설치 확인
    if not check_playwright_installed():
        logger.warning("Playwright가 설치되지 않았거나 초기화에 실패했습니다. 일부 페이지가 올바르게 수집되지 않을 수 있습니다.")
    
    # 테스트 모드 확인
    if args.test:
        print("테스트 모드로 실행합니다.")
        test_crawling()
        return
    
    base_url = "https://www.gov.kr/search/applyMw?Mcode=11166"
    
    # 워커 수 설정
    cpu_count = os.cpu_count() or 4
    page_workers = min(5, cpu_count) if args.workers == 0 else args.workers
    detail_workers = min(5, cpu_count) if args.workers == 0 else args.workers
    batch_size = 30  # 배치 크기 축소 (너무 많은 동시 요청 방지)
    
    # 통계 정보 초기화
    stats = {
        "총_페이지": 0,
        "총_민원수": 0,
        "성공": 0,
        "실패": 0,
        "처리시간": 0,
        "시작시간": time.time()
    }
    
    processed_minwons = []  # 처리된 민원 목록 초기화
    
    try:
        # 첫 페이지에서 마지막 페이지 번호 가져오기
        logger.info(f"첫 페이지에서 정보 가져오는 중...")
        soup = get_page_content(base_url)
        if soup is None:
            logger.error("첫 페이지를 가져오지 못했습니다.")
            return
            
        last_page = get_last_page_number(soup.prettify())
        logger.info(f"총 {last_page} 페이지가 있습니다.")
        stats["총_페이지"] = last_page
        
        # 특정 페이지만 크롤링
        if args.page > 0:
            logger.info(f"페이지 {args.page}만 크롤링합니다.")
            last_page = args.page
            soup = get_page_content(get_page_url(base_url, args.page))
            minwon_list = extract_minwon_list(soup.prettify())
            logger.info(f"페이지 {args.page}에서 {len(minwon_list)}개 민원 추출")
        else:
            # 페이지 데이터 수집
            logger.info(f"모든 페이지의 민원 목록 수집 중 (병렬 처리: {page_workers}개 워커)...")
            minwon_list = fetch_pages_parallel(base_url, last_page, page_workers)
        
        stats["총_민원수"] = len(minwon_list)
        logger.info(f"총 {stats['총_민원수']}개의 민원이 추출되었습니다.")
        
        # 민원이 없으면 종료
        if not minwon_list:
            logger.error("추출된 민원이 없습니다.")
            return
            
        # 일부 샘플만 처리 (디버깅 목적)
        if args.page < 0:
            sample_size = min(10, len(minwon_list))
            logger.info(f"디버깅 모드: 처음 {sample_size}개 민원만 처리합니다.")
            minwon_list = minwon_list[:sample_size]
            stats["총_민원수"] = len(minwon_list)
        
        # 상세 정보 수집
        batches = [minwon_list[i:i + batch_size] for i in range(0, len(minwon_list), batch_size)]
        
        # 진행 상황 표시
        if TQDM_AVAILABLE:
            batch_iter = tqdm(batches, desc="민원 상세정보 배치 처리")
        else:
            batch_iter = batches
            logger.info(f"총 {len(batches)}개 배치로 나누어 처리합니다. (배치당 최대 {batch_size}개 항목)")
            
        for batch_idx, batch in enumerate(batch_iter, 1):
            if not TQDM_AVAILABLE:
                logger.info(f"배치 {batch_idx}/{len(batches)} 처리 중... (진행률: {batch_idx/len(batches)*100:.1f}%)")
            
            # NLP 활성화 여부에 따라 처리 모드 변경
            if args.nlp and (OKT_AVAILABLE or NLTK_AVAILABLE):
                logger.info("텍스트 분석 기능 활성화 상태로 처리합니다.")
                # 텍스트 분석이 필요하다는 정보를 global 변수로 설정
                set_nlp_enabled(True)
            else:
                # 명시적으로 NLP 비활성화
                set_nlp_enabled(False)
            
            batch_results = batch_process_minwons(batch, detail_workers)
            processed_minwons.extend(batch_results)
            
            # 진행 상황 통계 업데이트
            success_count = sum(1 for m in batch_results if "정상" in m.get("오류여부", "") or "성공" in m.get("오류여부", ""))
            fail_count = len(batch_results) - success_count
            stats["성공"] += success_count
            stats["실패"] += fail_count
            
            # 중간 진행 상황 출력
            current_time = time.time()
            elapsed = current_time - stats["시작시간"]
            if not TQDM_AVAILABLE:
                logger.info(f"진행 상황: 성공 {stats['성공']}건, 실패 {stats['실패']}건, 경과시간: {elapsed/60:.1f}분")
            
            # 중간 결과 저장 (배치당 한 번)
            if batch_idx % 2 == 0 or batch_idx == len(batches):
                checkpoint_file = os.path.join(output_dir, f"정부24_민원_진행상황_{batch_idx}of{len(batches)}.csv")
                save_checkpoint(processed_minwons, checkpoint_file)
        
        # 최종 통계 계산
        stats["처리시간"] = time.time() - stats["시작시간"]
        
        # 중복 민원 필터링 중...
        if processed_minwons:
            logger.info("중복 민원 필터링 중...")
            processed_minwons = filter_duplicate_minwons(processed_minwons)
            logger.info(f"필터링 후 총 {len(processed_minwons)}개 민원 항목 남음")
        
        # 결과 저장
        output_file = os.path.join(output_dir, "정부24_민원목록.csv")
        save_to_csv(processed_minwons, output_file)
        logger.info(f"모든 민원 데이터가 저장되었습니다: {output_file}")
        
        # 오류 목록 별도 저장
        error_items = [m for m in processed_minwons if "정상" not in m.get("오류여부", "") and "성공" not in m.get("오류여부", "")]
        if error_items:
            error_file = os.path.join(output_dir, "정부24_민원목록_오류.csv")
            save_to_csv(error_items, error_file)
            logger.info(f"오류 항목 {len(error_items)}개를 별도 저장했습니다: {error_file}")
        
        # 최종 통계 출력
        logger.info("=" * 50)
        logger.info("민원 수집 완료")
        logger.info(f"총 처리 민원: {stats['총_민원수']}건")
        logger.info(f"성공: {stats['성공']}건 ({stats['성공']/stats['총_민원수']*100 if stats['총_민원수'] else 0:.1f}%)")
        logger.info(f"실패: {stats['실패']}건 ({stats['실패']/stats['총_민원수']*100 if stats['총_민원수'] else 0:.1f}%)")
        logger.info(f"총 소요시간: {stats['처리시간']/60:.1f}분")
        logger.info("=" * 50)
        
    except KeyboardInterrupt:
        # 사용자가 작업을 중단한 경우
        elapsed = time.time() - stats["시작시간"]
        logger.warning("사용자가 작업을 중단했습니다.")
        
        # 현재까지의 결과 저장
        if processed_minwons:
            interrupt_file = os.path.join(output_dir, "정부24_민원목록_중단됨.csv")
            save_to_csv(processed_minwons, interrupt_file)
            logger.info(f"중단 시점까지의 {len(processed_minwons)}개 결과를 저장했습니다: {interrupt_file}")
        
        # 중단 시점의 통계 출력
        logger.info("=" * 50)
        logger.info("작업 중단 통계")
        logger.info(f"처리된 민원: {len(processed_minwons)}/{stats['총_민원수']}건 ({len(processed_minwons)/stats['총_민원수']*100 if stats['총_민원수'] else 0:.1f}%)")
        logger.info(f"경과 시간: {elapsed/60:.1f}분")
        logger.info("=" * 50)
    except Exception as e:
        # 예상치 못한 오류 발생
        logger.error(f"프로그램 실행 중 오류 발생: {str(e)}")
        
        # 현재까지의 결과 저장
        if processed_minwons:
            error_file = os.path.join(output_dir, "정부24_민원목록_오류발생.csv")
            save_to_csv(processed_minwons, error_file)
            logger.info(f"오류 발생 시점까지의 {len(processed_minwons)}개 결과를 저장했습니다: {error_file}")
        
        # 스택 트레이스 출력
        logger.error("상세 오류 정보:")
        logger.error(traceback.format_exc())

# 중복 민원 필터링 함수 추가
def filter_duplicate_minwons(minwon_list):
    """유사한 민원을 식별하고 병합하는 함수"""
    unique_minwons = {}
    duplicates_count = 0
    
    for minwon in minwon_list:
        # 민원명과 담당부서로 고유 키 생성
        key = f"{minwon.get('민원명', '')}_{minwon.get('담당부서', '')}"
        
        if key in unique_minwons:
            # 기존 항목이 있으면 일련번호와 링크 정보 병합
            duplicates_count += 1
            existing = unique_minwons[key]
            
            # 일련번호 목록 유지
            tp_seq_list = set([existing.get('일련번호', ''), minwon.get('일련번호', '')])
            tp_seq_list.discard('')  # 빈 값 제거
            existing['일련번호'] = ', '.join(tp_seq_list)
            
            # 링크 정보가 다르면 추가 정보로 저장
            if existing.get('링크') != minwon.get('링크') and minwon.get('링크'):
                existing['연관민원'] = existing.get('연관민원', '') + f" | {minwon.get('링크')}"
            
            # 더 상세한 설명 선택
            if len(minwon.get('설명', '')) > len(existing.get('설명', '')):
                existing['설명'] = minwon.get('설명', '')
            
            # 추가 정보 병합 (비어있는 필드 채우기)
            for field in ['처리절차', '신청방법', '필요서류', '수수료']:
                if not existing.get(field) and minwon.get(field):
                    existing[field] = minwon.get(field)
        else:
            # 새로운 항목 추가
            unique_minwons[key] = minwon
    
    logger.info(f"중복 필터링: {duplicates_count}개 중복 항목 검출, {len(unique_minwons)}개 고유 항목 유지")
    return list(unique_minwons.values())

# NLP 활성화 상태 저장용 변수 추가
NLP_ENABLED = False

def main():
    """메인 함수 (개선됨)"""
    # 명령행 인자 파싱
    parser = argparse.ArgumentParser(description="정부24 민원 수집 프로그램")
    parser.add_argument("--output", default="~/Desktop/data", help="출력 디렉토리 경로")
    parser.add_argument("--test", action="store_true", help="테스트 모드로 실행")
    parser.add_argument("--page", type=int, default=0, help="특정 페이지만 크롤링 (0=전체)")
    parser.add_argument("--workers", type=int, default=0, help="병렬 처리에 사용할 워커 수 (0=자동)")
    parser.add_argument("--nlp", action="store_true", help="텍스트 분석 강화 모드 사용")
    parser.add_argument("--cli", action="store_true", help="대화형 CLI 모드로 실행")
    args = parser.parse_args()
    
    # 대화형 CLI 모드 여부 확인
    if args.cli or len(sys.argv) == 1:  # 인자가 없거나 --cli 옵션이 있으면 대화형 모드 실행
        cli = InteractiveCLI()
        cli.run()
        return
    
    # 명령행 인자 모드로 실행 시 NLP 설정
    set_nlp_enabled(args.nlp)
    run_crawler_with_args(args)

if __name__ == "__main__":
    main()