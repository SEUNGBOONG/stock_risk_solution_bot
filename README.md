# stock_risk_solution_bot

한국투자증권 API 연동 기반으로 통합 포트폴리오를 분석하고, 결과를 Slack/Notion으로 자동 리포팅하는 프로젝트입니다.

## What It Does

- 일반 위탁 + ISA 계좌 포지션 통합 조회 (KIS API)
- 95% VaR, 위기 스트레스 손실 추정, 액션 가이드 생성
- 보유 종목 상관관계 행렬 및 분산 조언
- 국내/나스닥 저평가 스캔 (PER/PBR/ROE/배당 기반 점수화)
- USD/KRW 환율 적정성 분석
- Slack 요약 전송 + Notion DB 기록
- GitHub Actions: **국내장 개장** / **미국장 개장** 각각 스케줄 + 수동 통합 실행
- Slack: **통합 1통 + 계좌별 메시지 분리** (같은 실행에서 연속 전송)
- Notion: 실행마다 TOTAL + 각 계좌 행, 제목에 `[국내장]` / `[미국장]` / `[통합]` 구분

## GitHub Actions 워크플로

| 파일 | 설명 |
|------|------|
| `portfolio-kr-open.yml` | 평일 **KST 09:00** 직후 — `RUN_MODE=domestic` (국내 PER/PBR 스캔 + 포트폴리오) |
| `portfolio-us-open.yml` | 평일 **UTC 14:35** — `RUN_MODE=overseas` (나스닥 스캔 + 포트폴리오, NY 시간대와 약간 오차 가능) |
| `daily-analysis.yml` | **수동만** — `full` / `domestic` / `overseas` 선택 |

GitHub `schedule`은 **UTC**만 지원합니다. 미국장 시각을 더 맞추려면 서머타임에 맞춰 `portfolio-us-open.yml`의 cron을 분기(또는 추가 워크플로)하면 됩니다.

### 알림이 한 번만 온 경우

- 해당 시각 워크플로가 **실패**했는지 Actions 로그에서 확인 (yfinance/한투 API 타임아웃 등).
- 저장소가 **60일간 비활성**이면 GitHub이 scheduled workflow를 중지할 수 있습니다.
- 포크 저장소는 기본적으로 `schedule`이 비활성일 수 있습니다.

## 환경 변수

로컬 `.env`에서 선택:

- `RUN_MODE=full` — 국내·나스닥 스캔 모두
- `RUN_MODE=domestic` — 국내 스캔만 (국내장용)
- `RUN_MODE=overseas` — 나스닥 스캔만 (미국장용)

## Quick Start

1) Python 설치 후 의존성 설치

```bash
pip install -r requirements.txt
```

2) `.env.example`을 참고해 `.env` 생성

3) 로컬 실행

```bash
python -m src.main
```

## GitHub Actions Secrets

다음 시크릿을 저장소에 등록하세요.

- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNEL_ID`
- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- `KIS_BASE_URL` (예: `https://openapi.koreainvestment.com:9443`)
- `KIS_ACCOUNTS` (예: `BROKER_MAIN:12345678:01:domestic,ISA_MAIN:12345678:11:overseas`)

## Notion DB Schema (예시)

아래 property 이름을 코드와 동일하게 맞추면 바로 저장됩니다.

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