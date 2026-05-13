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
from .reporting import insert_notion_rows, post_slack_separate_reports


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
    mode = settings.run_mode
    domestic_picks: list = []
    nasdaq_picks: list = []
    if mode in ("full", "domestic"):
        domestic_picks = undervalued_scan(kospi_universe, top_n=5)
    if mode in ("full", "overseas"):
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

    post_slack_separate_reports(
        settings.slack_bot_token,
        settings.slack_channel_id,
        mode,
        risk,
        domestic_picks,
        nasdaq_picks,
        corr,
        corr_advice,
        fx,
        account_results,
    )
    insert_notion_rows(
        settings.notion_token,
        settings.notion_database_id,
        mode,
        risk,
        domestic_picks,
        nasdaq_picks,
        corr_advice,
        fx,
        account_results,
    )


if __name__ == "__main__":
    run()
