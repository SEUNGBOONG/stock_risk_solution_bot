# stock_risk_solution_bot

한국투자증권(KIS) 계좌 잔고를 가져와 포트폴리오 리스크를 계산하고, Slack/Notion으로 결과를 전송하는 자동 분석 봇입니다.

## 현재 구조

```text
.
├── .github/workflows/
│   ├── ci.yml                    # Push/PR 빌드 검증: 의존성 설치 + compileall
│   ├── daily-analysis.yml         # 수동 실행: full/domestic/overseas 선택
│   ├── portfolio-kr-open.yml      # 국내장 개장 직후 스케줄 실행
│   └── portfolio-us-open.yml      # 미국장 개장 직후 스케줄 실행
├── data/universes/
│   ├── kospi200_sample.txt        # 국내 저평가 스캔 대상 샘플
│   └── nasdaq100_sample.txt       # 나스닥 저평가 스캔 대상 샘플
├── src/
│   ├── main.py                    # 실행 진입점
│   ├── config.py                  # 환경변수 로딩 및 계좌 설정 파싱
│   ├── kis_client.py              # KIS 잔고 조회 클라이언트
│   ├── analytics.py               # VaR, 스트레스 손실, 상관관계, 저평가/환율 분석
│   └── reporting.py               # Slack/Notion 메시지 생성 및 전송
├── requirements.txt
└── .env.example
```

## 실행 흐름

1. `src.main`이 환경변수를 읽어 설정을 구성합니다.
2. `KisClient`가 KIS API 또는 mock 데이터로 계좌별 포지션을 가져옵니다.
3. `analytics.py`가 전체/계좌별 리스크, 상관관계, 저평가 후보, USD/KRW 상태를 계산합니다.
4. `reporting.py`가 Slack 메시지와 Notion 페이지를 생성합니다.

## GitHub Actions

| 파일 | 목적 |
| --- | --- |
| `ci.yml` | 코드 빌드 검증 전용. Push/PR에서 실행되며 외부 계좌 API를 호출하지 않습니다. |
| `daily-analysis.yml` | 수동 분석 실행. `full`, `domestic`, `overseas` 중 선택합니다. |
| `portfolio-kr-open.yml` | 평일 KST 09:00에 `RUN_MODE=domestic`으로 실행합니다. |
| `portfolio-us-open.yml` | 평일 UTC 14:35에 `RUN_MODE=overseas`로 실행합니다. 미국 DST 기간에는 시간이 1시간 어긋날 수 있습니다. |

운영 워크플로는 실제 KIS/Slack/Notion API를 호출합니다. Secrets가 없거나 API가 실패하면 실패하는 것이 정상입니다. 코드 빌드 가능 여부는 `CI` 워크플로에서 확인합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python -m src.main
```

`.env.example`을 참고해 `.env`를 만들면 됩니다.

## 필요한 GitHub Secrets

- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNEL_ID`
- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- `KIS_BASE_URL`
- `KIS_ACCOUNTS`

`KIS_ACCOUNTS` 형식:

```text
alias:cano:acnt_prdt_cd:market
```

예:

```text
BROKER_MAIN:12345678:01:domestic,ISA_MAIN:12345678:11:overseas
```

## Notion DB Schema 예시

- `Name` (title)
- `Date` (date)
- `TotalAsset` (number)
- `VaR95` (number)
- `StressLoss` (number)
- `DomesticTop5` (rich_text)
- `NasdaqTop5` (rich_text)
- `CorrelationAdvice` (rich_text)
- `FxView` (rich_text)
- `Summary` (rich_text)
