from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
import pandas as pd

from .analytics import RiskResult, format_picks_for_slack


def _session_label(run_mode: str) -> str:
    if run_mode == "domestic":
        return "국내장"
    if run_mode == "overseas":
        return "미국장"
    return "통합"


def _corr_block(corr: pd.DataFrame, corr_advice: str) -> str:
    corr_txt = "n/a"
    if not corr.empty:
        corr_txt = corr.to_string(max_rows=8, max_cols=8)
    return f"*상관관계 관리* {corr_advice}\n```{corr_txt}```\n"


def _quant_block(
    run_mode: str,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
) -> str:
    empty = "데이터 없음 (지표 부족 또는 외부 API 응답 없음)"
    if run_mode == "domestic":
        body = format_picks_for_slack(domestic_picks, empty)
        return f"*국내 저평가 스캔 (PER/PBR/ROE/배당 점수)*\n{body}\n"
    if run_mode == "overseas":
        body = format_picks_for_slack(nasdaq_picks, empty)
        return f"*나스닥 저평가 스캔 (PER/PBR/ROE/배당 점수)*\n{body}\n"
    d = format_picks_for_slack(domestic_picks, empty)
    n = format_picks_for_slack(nasdaq_picks, empty)
    return f"*국내 저평가 TOP*\n{d}\n\n*나스닥 저평가 TOP*\n{n}\n"


def _build_account_sections(
    account_results: Dict[str, Dict[str, RiskResult | str]]
) -> str:
    if not account_results:
        return "- 계좌별 분석 결과 없음\n"
    lines: List[str] = []
    for alias, row in sorted(account_results.items()):
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


def format_slack_message_total(
    run_mode: str,
    risk: RiskResult,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
    corr: pd.DataFrame,
    corr_advice: str,
    fx: Dict[str, float | str],
    account_results: Dict[str, Dict[str, RiskResult | str]],
) -> str:
    session = _session_label(run_mode)
    account_sections = _build_account_sections(account_results)
    quant = _quant_block(run_mode, domestic_picks, nasdaq_picks)
    return (
        f"*[포트폴리오 리스크] {session}*\n"
        f"- 총자산: {risk.total_asset_krw:,.0f} KRW\n"
        f"- 95% VaR(1D): {risk.var_95_krw:,.0f} KRW\n"
        f"- 스트레스 손실(위기 시나리오): {risk.stress_loss_krw:,.0f} KRW\n"
        f"- 가이드: {risk.action_guide}\n\n"
        "*계좌별 요약 (상세는 아래 메시지)*\n"
        f"{account_sections}\n"
        f"{quant}"
        f"{_corr_block(corr, corr_advice)}"
        "*환율 분석*\n"
        f"- 현재 USD/KRW: {float(fx['current']):.2f}\n"
        f"- MA20: {float(fx['ma20']):.2f}, "
        f"MA120: {float(fx['ma120']):.2f}, "
        f"1Y 평균: {float(fx['mean_1y']):.2f}\n"
        f"- 전략: {fx['view']}"
    )


def format_slack_message_account(
    run_mode: str,
    alias: str,
    risk: RiskResult,
    corr_advice: str,
    fx: Dict[str, float | str],
) -> str:
    session = _session_label(run_mode)
    return (
        f"*[포트폴리오/{alias}] {session}*\n"
        f"- 자산: {risk.total_asset_krw:,.0f} KRW\n"
        f"- 95% VaR(1D): {risk.var_95_krw:,.0f} KRW\n"
        f"- 스트레스 손실: {risk.stress_loss_krw:,.0f} KRW\n"
        f"- 가이드: {risk.action_guide}\n"
        f"- 분산 조언: {corr_advice}\n\n"
        "*환율 (참고)*\n"
        f"- USD/KRW {float(fx['current']):.2f} -> {fx['view']}"
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


def post_slack_separate_reports(
    token: str,
    channel_id: str,
    run_mode: str,
    risk: RiskResult,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
    corr: pd.DataFrame,
    corr_advice: str,
    fx: Dict[str, float | str],
    account_results: Dict[str, Dict[str, RiskResult | str]],
) -> None:
    if not token or not channel_id:
        return
    post_to_slack(
        token,
        channel_id,
        format_slack_message_total(
            run_mode=run_mode,
            risk=risk,
            domestic_picks=domestic_picks,
            nasdaq_picks=nasdaq_picks,
            corr=corr,
            corr_advice=corr_advice,
            fx=fx,
            account_results=account_results,
        ),
    )
    for alias, row in sorted(account_results.items()):
        ar = row["risk"]
        ca = row["corr_advice"]
        if not isinstance(ar, RiskResult):
            continue
        post_to_slack(
            token,
            channel_id,
            format_slack_message_account(run_mode, alias, ar, str(ca), fx),
        )


def _notion_headers(notion_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _fetch_notion_schema(
    client: httpx.Client, notion_token: str, database_id: str
) -> Dict[str, Any]:
    res = client.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=_notion_headers(notion_token),
    )
    res.raise_for_status()
    return res.json().get("properties", {})


def _title_property_name(schema: Dict[str, Any]) -> str | None:
    for name, meta in schema.items():
        if meta.get("type") == "title":
            return name
    return None


def _add_if_supported(
    props: Dict[str, Any],
    schema: Dict[str, Any],
    name: str,
    notion_type: str,
    value: Any,
) -> None:
    if schema.get(name, {}).get("type") != notion_type:
        return
    if notion_type == "number":
        props[name] = {"number": float(value)}
    elif notion_type == "date":
        props[name] = {"date": {"start": str(value)}}
    elif notion_type == "rich_text":
        props[name] = {"rich_text": [{"text": {"content": str(value)[:1900]}}]}


def _create_notion_page(
    client: httpx.Client,
    notion_token: str,
    database_id: str,
    schema: Dict[str, Any],
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
    title_name = _title_property_name(schema)
    if not title_name:
        raise RuntimeError("Notion database has no title property")

    now = datetime.now(timezone.utc).date().isoformat()
    props: Dict[str, Any] = {
        title_name: {"title": [{"text": {"content": title[:200]}}]},
    }
    _add_if_supported(props, schema, "Date", "date", now)
    _add_if_supported(props, schema, "TotalAsset", "number", total_asset_krw)
    _add_if_supported(props, schema, "VaR95", "number", var_95_krw)
    _add_if_supported(props, schema, "StressLoss", "number", stress_loss_krw)
    _add_if_supported(props, schema, "DomesticTop5", "rich_text", domestic_top5)
    _add_if_supported(props, schema, "NasdaqTop5", "rich_text", nasdaq_top5)
    _add_if_supported(props, schema, "CorrelationAdvice", "rich_text", corr_advice)
    _add_if_supported(props, schema, "FxView", "rich_text", fx_view)
    _add_if_supported(props, schema, "Summary", "rich_text", summary)

    payload = {
        "parent": {"database_id": database_id},
        "properties": props,
    }
    res = client.post(
        "https://api.notion.com/v1/pages",
        headers=_notion_headers(notion_token),
        json=payload,
    )
    if res.status_code >= 400:
        raise RuntimeError(f"Notion page create failed: {res.status_code} {res.text[:1000]}")


def _picks_compact_with_metrics(picks: List[Dict[str, float | str]]) -> str:
    if not picks:
        return ""
    parts: List[str] = []
    for p in picks:
        parts.append(
            f"{p['symbol']}(PER{float(p['per']):.1f}/PBR{float(p['pbr']):.2f})"
        )
    return ", ".join(parts)


def insert_notion_rows(
    notion_token: str,
    database_id: str,
    run_mode: str,
    risk: RiskResult,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
    corr_advice: str,
    fx: Dict[str, float | str],
    account_results: Dict[str, Dict[str, RiskResult | str]],
) -> None:
    if not notion_token or not database_id:
        return

    try:
        with httpx.Client(timeout=20.0) as client:
            schema = _fetch_notion_schema(client, notion_token, database_id)
            _insert_notion_rows_with_schema(
                client,
                notion_token,
                database_id,
                schema,
                run_mode,
                risk,
                domestic_picks,
                nasdaq_picks,
                corr_advice,
                fx,
                account_results,
            )
    except Exception as exc:
        print(f"[notion] warning: Notion write skipped: {exc}")


def _insert_notion_rows_with_schema(
    client: httpx.Client,
    notion_token: str,
    database_id: str,
    schema: Dict[str, Any],
    run_mode: str,
    risk: RiskResult,
    domestic_picks: List[Dict[str, float | str]],
    nasdaq_picks: List[Dict[str, float | str]],
    corr_advice: str,
    fx: Dict[str, float | str],
    account_results: Dict[str, Dict[str, RiskResult | str]],
) -> None:
    session = _session_label(run_mode)
    dom_detail = format_picks_for_slack(domestic_picks, "")
    nas_detail = format_picks_for_slack(nasdaq_picks, "")
    dom_compact = _picks_compact_with_metrics(domestic_picks)
    nas_compact = _picks_compact_with_metrics(nasdaq_picks)
    account_sections = _build_account_sections(account_results).strip()
    total_summary = (
        f"[{session}] 가이드: {risk.action_guide}\n"
        f"계좌별\n{account_sections}\n"
        f"국내:\n{dom_detail or '(생략)'}\n"
        f"나스닥:\n{nas_detail or '(생략)'}\n"
        f"상관: {corr_advice}\n환율: {fx['view']}"
    )
    _create_notion_page(
        client=client,
        notion_token=notion_token,
        database_id=database_id,
        schema=schema,
        title=f"Portfolio - TOTAL [{session}]",
        total_asset_krw=risk.total_asset_krw,
        var_95_krw=risk.var_95_krw,
        stress_loss_krw=risk.stress_loss_krw,
        domestic_top5=dom_compact or "(생략)",
        nasdaq_top5=nas_compact or "(생략)",
        corr_advice=corr_advice,
        fx_view=str(fx["view"]),
        summary=total_summary,
    )

    for alias, row in sorted(account_results.items()):
        alias_risk = row["risk"]
        alias_corr_advice = row["corr_advice"]
        if not isinstance(alias_risk, RiskResult):
            continue
        alias_summary = (
            f"[{session}] 계좌 {alias}\n"
            f"가이드: {alias_risk.action_guide}\n"
            f"상관: {alias_corr_advice}\n환율: {fx['view']}"
        )
        _create_notion_page(
            client=client,
            notion_token=notion_token,
            database_id=database_id,
            schema=schema,
            title=f"Portfolio - {alias} [{session}]",
            total_asset_krw=alias_risk.total_asset_krw,
            var_95_krw=alias_risk.var_95_krw,
            stress_loss_krw=alias_risk.stress_loss_krw,
            domestic_top5=dom_compact or "(생략)",
            nasdaq_top5=nas_compact or "(생략)",
            corr_advice=str(alias_corr_advice),
            fx_view=str(fx["view"]),
            summary=alias_summary,
        )
