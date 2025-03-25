# 정부24 민원 크롤러

정부24 웹사이트에서 민원 및 정부 서비스 정보를 수집하는 크롤링 도구입니다. 민원명, 신청방법, 처리절차, 필요서류 등 상세 정보를 자동으로 수집하여 분석 가능한 형태로 저장합니다.

## 주요 기능

- 정부24 민원/서비스 목록 및 상세 정보 수집
- 대화형 CLI 모드 제공 (사용자 친화적 인터페이스)
- 멀티스레드 병렬 처리 지원
- Playwright를 활용한 JavaScript 기반 페이지 처리
- NLP(자연어 처리) 기반 텍스트 분석 및 품질 개선 (선택적)
- CSV 형식으로 데이터 저장

## 설치 방법

### 1. 요구 사항

- Python 3.7 이상
- pip (Python 패키지 관리자)

### 2. 저장소 복제

```bash
git clone https://github.com/yourusername/hanolcare-crawler.git
cd hanolcare-crawler
```

### 3. 필수 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. Playwright 브라우저 설치

```bash
python -m playwright install
```

### 5. NLP 기능을 위한 Java 설정 (선택적)

한국어 텍스트 분석을 위해 Java JDK와 KoNLPy 설정이 필요합니다:

```bash
# Java 설치 도움말 실행
bash scripts/java_setup.sh
```

## 사용 방법

### 대화형 CLI 모드 (권장)

가장 쉬운 방법은 대화형 CLI 모드를 사용하는 것입니다:

```bash
python src/crawler.py
```

또는

```bash
bash scripts/run.sh
```

대화형 메뉴를 통해 다음 설정을 구성할 수 있습니다:
- 크롤링 모드 (전체 페이지/특정 페이지/테스트 모드/특정 URL)
- 출력 경로
- 병렬 처리 워커 수
- 텍스트 분석 기능 활성화 여부
- 배치 크기

### 명령행 인자 모드

특정 옵션으로 직접 실행하려면:

```bash
python src/crawler.py --output ~/data --workers 5 --nlp
```

#### 주요 옵션

- `--output`: 결과 저장 경로 (기본값: ~/Desktop/data)
- `--test`: 테스트 모드로 실행 (샘플 URL만 처리)
- `--page`: 특정 페이지만 크롤링 (0=전체)
- `--workers`: 병렬 처리 워커 수 (0=자동)
- `--nlp`: 텍스트 분석 기능 활성화
- `--cli`: 대화형 CLI 모드 실행

## 출력 파일

크롤링 결과는 기본적으로 `~/Desktop/data` 디렉토리에 저장됩니다:

- `정부24_민원목록.csv`: 성공적으로 수집된 모든 민원 정보
- `정부24_민원목록_오류.csv`: 오류가 발생한 민원 정보
- `정부24_민원_진행상황.csv`: 크롤링 진행 중 생성되는 체크포인트 파일

## 문제 해결

### 자주 발생하는 문제

1. **Playwright 관련 오류**
   ```
   pip install playwright
   python -m playwright install
   ```

2. **KoNLPy/Java 관련 오류**
   ```
   bash scripts/java_setup.sh
   ```
   스크립트의 안내에 따라 Java JDK를 설치하고 JAVA_HOME 환경 변수를 설정하세요.

3. **크롤링 중 네트워크 오류**
   - 네트워크 연결 상태를 확인하세요
   - `--workers` 값을 줄여 동시 요청 수를 제한하세요

## 개발 정보

- Python 3.7+
- 주요 사용 라이브러리: requests, BeautifulSoup4, Playwright, tqdm
- 선택적 라이브러리: KoNLPy, JPype1, NLTK

## 라이선스

MIT License