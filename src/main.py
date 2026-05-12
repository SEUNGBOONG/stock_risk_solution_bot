from __future__ import annotations

from pathlib import Path

from .analytics import (
    build_diversification_advice,
    calc_correlation_matrix,
    calc_risk_metrics,
    fx_fairness_analysis,
    undervalued_scan,
)
from .config import load_settings
from .kis_client import KisClient
from .reporting import format_slack_text, insert_notion_rows, post_to_slack


def _load_universe(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def run() -> None:
    settings = load_settings()
    client = KisClient(settings)

    positions = client.fetch_all_positions()
    risk = calc_risk_metrics(positions)
    corr = calc_correlation_matrix(positions)
    corr_advice = build_diversification_advice(corr)

    kospi_universe = _load_universe("data/universes/kospi200_sample.txt")
    nasdaq_universe = _load_universe("data/universes/nasdaq100_sample.txt")
    domestic_picks = undervalued_scan(kospi_universe, top_n=5)
    nasdaq_picks = undervalued_scan(nasdaq_universe, top_n=5)

    fx = fx_fairness_analysis()
    account_results = {}
    account_aliases = sorted(set([p.account_alias for p in positions]))
    for alias in account_aliases:
        account_positions = [p for p in positions if p.account_alias == alias]
        alias_risk = calc_risk_metrics(account_positions)
        alias_corr = calc_correlation_matrix(account_positions)
        alias_corr_advice = build_diversification_advice(alias_corr)
        account_results[alias] = {"risk": alias_risk, "corr_advice": alias_corr_advice}

    slack_text = format_slack_text(
        risk=risk,
        domestic_picks=domestic_picks,
        nasdaq_picks=nasdaq_picks,
        corr=corr,
        corr_advice=corr_advice,
        fx=fx,
        account_results=account_results,
    )
    post_to_slack(settings.slack_bot_token, settings.slack_channel_id, slack_text)
    insert_notion_rows(
        settings.notion_token,
        settings.notion_database_id,
        risk,
        domestic_picks,
        nasdaq_picks,
        corr_advice,
        fx,
        account_results,
    )


if __name__ == "__main__":
    run()
