from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AccountConfig:
    alias: str
    cano: str
    acnt_prdt_cd: str
    market: str  # domestic | overseas | all
    app_key: str
    app_secret: str


@dataclass(frozen=True)
class Settings:
    notion_token: str
    notion_database_id: str
    slack_bot_token: str
    slack_channel_id: str
    kis_app_key: str
    kis_app_secret: str
    kis_base_url: str
    kis_accounts: List[AccountConfig]
    use_mock_balance: bool
    # full | domestic | overseas. GitHub Actions sets this per workflow.
    run_mode: str


def _parse_accounts(raw: str) -> List[AccountConfig]:
    if not raw.strip():
        return []
    out: List[AccountConfig] = []
    for chunk in raw.split(","):
        parts = [x.strip() for x in chunk.split(":")]
        if len(parts) not in {3, 4, 5, 6}:
            raise ValueError(f"Invalid KIS_ACCOUNTS item: {chunk}")
        alias, cano, acnt_prdt_cd = parts[:3]
        market = "all"
        app_key = os.getenv("KIS_APP_KEY", "")
        app_secret = os.getenv("KIS_APP_SECRET", "")

        if len(parts) == 4:
            market = parts[3]
        elif len(parts) == 5:
            app_key = _secret_value(parts[3])
            app_secret = _secret_value(parts[4])
        elif len(parts) == 6:
            market = parts[3]
            app_key = _secret_value(parts[4])
            app_secret = _secret_value(parts[5])

        if market not in {"domestic", "overseas", "all"}:
            raise ValueError(f"Invalid market for account {alias}: {market}")
        out.append(
            AccountConfig(
                alias=alias,
                cano=cano,
                acnt_prdt_cd=acnt_prdt_cd,
                market=market,
                app_key=app_key,
                app_secret=app_secret,
            )
        )
    return out


def _secret_value(name_or_value: str) -> str:
    value = os.getenv(name_or_value)
    if value is not None:
        return value
    if name_or_value.startswith("KIS_"):
        return ""
    return name_or_value


def load_settings() -> Settings:
    mode = os.getenv("RUN_MODE", "full").strip().lower()
    if mode not in {"full", "domestic", "overseas"}:
        mode = "full"
    settings = Settings(
        notion_token=os.getenv("NOTION_TOKEN", ""),
        notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
        slack_channel_id=os.getenv("SLACK_CHANNEL_ID", ""),
        kis_app_key=os.getenv("KIS_APP_KEY", ""),
        kis_app_secret=os.getenv("KIS_APP_SECRET", ""),
        kis_base_url=os.getenv(
            "KIS_BASE_URL", "https://openapi.koreainvestment.com:9443"
        ),
        kis_accounts=_parse_accounts(os.getenv("KIS_ACCOUNTS", "")),
        use_mock_balance=os.getenv("USE_MOCK_BALANCE", "false").lower() == "true",
        run_mode=mode,
    )
    _validate_settings(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    missing = []
    if not settings.kis_base_url:
        missing.append("KIS_BASE_URL")
    if not settings.kis_accounts and not settings.use_mock_balance:
        missing.append("KIS_ACCOUNTS")
    for account in settings.kis_accounts:
        if not account.app_key:
            missing.append(f"{account.alias}.app_key")
        if not account.app_secret:
            missing.append(f"{account.alias}.app_secret")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
