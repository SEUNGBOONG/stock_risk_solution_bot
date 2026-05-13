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
    market: str  # domestic | overseas


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
        if len(parts) != 4:
            raise ValueError(f"Invalid KIS_ACCOUNTS item: {chunk}")
        alias, cano, acnt_prdt_cd, market = parts
        if market not in {"domestic", "overseas"}:
            raise ValueError(f"Invalid market for account {alias}: {market}")
        out.append(
            AccountConfig(
                alias=alias,
                cano=cano,
                acnt_prdt_cd=acnt_prdt_cd,
                market=market,
            )
        )
    return out


def load_settings() -> Settings:
    mode = os.getenv("RUN_MODE", "full").strip().lower()
    if mode not in {"full", "domestic", "overseas"}:
        mode = "full"
    return Settings(
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
