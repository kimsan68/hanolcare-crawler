# 정부24 민원 데이터 재크롤링 및 품질 개선 도구

## 사용 방법

### 1. 기본 재크롤링 실행

```bash
python enhanced_crawler.py
```

이 명령은 다음 작업을 수행합니다:
- 기존 CSV 파일에서 불완전한 데이터 식별
- 누락된 필드(신청방법, 필요서류, 수수료, 처리기간 등)가 있는 항목 재크롤링
- 결과를 `improved_data` 디렉토리에 저장

### 2. 오류 URL 재시도

```bash
python run_recrawl.py --retry
```

이전 크롤링에서 실패한 URL을 재시도합니다.

### 3. 데이터 품질 분석

```bash
python quality_check.py
```

원본 데이터와 개선된 데이터의 품질을 비교하고 보고서를 생성합니다.

## 고급 옵션

### enhanced_crawler.py 옵션

```bash
python enhanced_crawler.py --debug --workers 10
```

- `--debug`: 디버그 모드 활성화 (자세한 로그 출력)
- `--workers`: 병렬 작업자 수 설정 (기본값: 5)

### run_recrawl.py 옵션

```bash
python run_recrawl.py --workers 8 --prefix "hanolcare-v0.3" --retry
```

- `--workers`: 병렬 작업자 수 설정 (기본값: 5)
- `--prefix`: 출력 파일 접두어 설정 (기본값: "hanolcare-v0.2-beta")
- `--retry`: 이전 오류 URL 재시도
- `--debug`: 디버그 모드 활성화

### quality_check.py 옵션

```bash
python quality_check.py --dir "원본데이터경로" --output "보고서경로"
```

- `--dir`: 원본 데이터 디렉토리 (기본값: 현재 디렉토리)
- `--output`: 보고서 출력 디렉토리 (기본값: "quality_reports")

## 출력 파일

- **CSV**: 데이터 분석 및 시각화에 적합
- **JSON**: API 데이터 형식
- **JSONL**: 대용량 데이터 처리에 최적화된 형식

## 문제 해결

크롤링 중 오류가 발생할 경우:

1. `crawler_log.txt` 파일에서 자세한 오류 내용 확인
2. `--debug` 옵션을 사용하여 더 자세한 로그 확인
3. `improved_data/error_urls.txt`에 기록된 실패한 URL 확인 후 재시도

## 결과 확인

1. `improved_data` 디렉토리에서 크롤링 결과 확인
2. `quality_reports` 디렉토리에서 품질 분석 보고서 확인
