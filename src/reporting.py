from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

import httpx
import pandas as pd

from .analytics import RiskResult


def _build_account_sections(
    account_results: Dict[str, Dict[str, RiskResult | str]]
) -> str:
    if not account_results:
        return "- 계좌별 분석 결과 없음\n"
    lines: List[str] = []
    for alias, row in account_results.items():
        risk = row["risk"]
        corr_advice = row["corr_advice"]
        if not isinstance(risk, RiskResult):
            continue
        lines.append(
            (
                f"- [{alias}] 자산 {risk.total_asset_krw:,.0f} KRW | "
                f"VaR {risk.var_95_krw:,.0f} | "
                f"Stress {risk.stress_loss_krw:,.0f} | "
                f"가이드 {risk.action_guide} | "
                f"분산조언 {corr_advice}"
            )
        )
    return "\n".join(lines) + "\n"


def format_slack_text(
    risk: RiskResult,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
    corr: pd.DataFrame,
    corr_advice: str,
    fx: Dict[str, float | str],
    account_results: Dict[str, Dict[str, RiskResult | str]],
) -> str:
    dom_txt = ", ".join([str(x["symbol"]) for x in domestic_picks]) or "데이터 없음"
    nas_txt = ", ".join([str(x["symbol"]) for x in nasdaq_picks]) or "데이터 없음"
    corr_txt = "n/a"
    if not corr.empty:
        corr_txt = corr.to_string(max_rows=8, max_cols=8)
    account_sections = _build_account_sections(account_results)
    return (
        "*[통합 포트폴리오 일일 분석]*\n"
        f"- 총자산: {risk.total_asset_krw:,.0f} KRW\n"
        f"- 95% VaR(1D): {risk.var_95_krw:,.0f} KRW\n"
        f"- 스트레스 손실(위기 시나리오): {risk.stress_loss_krw:,.0f} KRW\n"
        f"- 가이드: {risk.action_guide}\n\n"
        "*계좌별 분리 분석*\n"
        f"{account_sections}\n"
        f"*국내 저평가 TOP5:* {dom_txt}\n"
        f"*나스닥 저평가 TOP5:* {nas_txt}\n\n"
        f"*상관관계 관제:* {corr_advice}\n"
        f"```{corr_txt}```\n\n"
        "*환율 분석*\n"
        f"- 현재 USD/KRW: {fx['current']:.2f}\n"
        f"- MA20: {fx['ma20']:.2f}, MA120: {fx['ma120']:.2f}, 1Y 평균: {fx['mean_1y']:.2f}\n"
        f"- 전략: {fx['view']}"
    )


def post_to_slack(token: str, channel_id: str, text: str) -> None:
    if not token or not channel_id:
        return
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"channel": channel_id, "text": text, "mrkdwn": True}
    with httpx.Client(timeout=20.0) as client:
        res = client.post(url, headers=headers, json=payload)
        res.raise_for_status()
        body = res.json()
        if not body.get("ok"):
            raise RuntimeError(f"Slack post failed: {body}")


def _create_notion_page(
    notion_token: str,
    database_id: str,
    title: str,
    total_asset_krw: float,
    var_95_krw: float,
    stress_loss_krw: float,
    domestic_top5: str,
    nasdaq_top5: str,
    corr_advice: str,
    fx_view: str,
    summary: str,
) -> None:
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    now = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": now}},
            "TotalAsset": {"number": total_asset_krw},
            "VaR95": {"number": var_95_krw},
            "StressLoss": {"number": stress_loss_krw},
            "DomesticTop5": {"rich_text": [{"text": {"content": domestic_top5}}]},
            "NasdaqTop5": {"rich_text": [{"text": {"content": nasdaq_top5}}]},
            "CorrelationAdvice": {"rich_text": [{"text": {"content": corr_advice[:1900]}}]},
            "FxView": {"rich_text": [{"text": {"content": fx_view[:1900]}}]},
            "Summary": {"rich_text": [{"text": {"content": summary[:1900]}}]},
        },
    }
    with httpx.Client(timeout=20.0) as client:
        res = client.post(url, headers=headers, json=payload)
        res.raise_for_status()


def insert_notion_rows(
    notion_token: str,
    database_id: str,
    risk: RiskResult,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
    corr_advice: str,
    fx: Dict[str, float | str],
    account_results: Dict[str, Dict[str, RiskResult | str]],
) -> None:
    if not notion_token or not database_id:
        return
    dom_txt = ", ".join([str(x["symbol"]) for x in domestic_picks])
    nas_txt = ", ".join([str(x["symbol"]) for x in nasdaq_picks])
    account_sections = _build_account_sections(account_results).strip()
    total_summary = (
        f"가이드: {risk.action_guide}\n"
        f"계좌별 분석:\n{account_sections}\n"
        f"국내 저평가: {dom_txt}\n"
        f"나스닥 저평가: {nas_txt}\n"
        f"상관관계 조언: {corr_advice}\n"
        f"환율 전략: {fx['view']}"
    )
    _create_notion_page(
        notion_token=notion_token,
        database_id=database_id,
        title="Portfolio Report - TOTAL",
        total_asset_krw=risk.total_asset_krw,
        var_95_krw=risk.var_95_krw,
        stress_loss_krw=risk.stress_loss_krw,
        domestic_top5=dom_txt,
        nasdaq_top5=nas_txt,
        corr_advice=corr_advice,
        fx_view=str(fx["view"]),
        summary=total_summary,
    )

    for alias, row in account_results.items():
        alias_risk = row["risk"]
        alias_corr_advice = row["corr_advice"]
        if not isinstance(alias_risk, RiskResult):
            continue
        alias_summary = (
            f"계좌: {alias}\n"
            f"가이드: {alias_risk.action_guide}\n"
            f"상관관계 조언: {alias_corr_advice}\n"
            f"환율 전략: {fx['view']}"
        )
        _create_notion_page(
            notion_token=notion_token,
            database_id=database_id,
            title=f"Portfolio Report - {alias}",
            total_asset_krw=alias_risk.total_asset_krw,
            var_95_krw=alias_risk.var_95_krw,
            stress_loss_krw=alias_risk.stress_loss_krw,
            domestic_top5=dom_txt,
            nasdaq_top5=nas_txt,
            corr_advice=str(alias_corr_advice),
            fx_view=str(fx["view"]),
            summary=alias_summary,
        )
