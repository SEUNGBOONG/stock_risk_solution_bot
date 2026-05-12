# stock_risk_solution_bot

한국투자증권 API 연동 기반으로 통합 포트폴리오를 분석하고, 결과를 Slack/Notion으로 자동 리포팅하는 프로젝트입니다.

## What It Does

- 일반 위탁 + ISA 계좌 포지션 통합 조회 (KIS API)
- 95% VaR, 위기 스트레스 손실 추정, 액션 가이드 생성
- 보유 종목 상관관계 행렬 및 분산 조언
- 국내/나스닥 저평가 스캔 (PER/PBR/ROE/배당 기반 점수화)
- USD/KRW 환율 적정성 분석
- Slack 요약 전송 + Notion DB 기록
- GitHub Actions로 장전/장후 자동 실행

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