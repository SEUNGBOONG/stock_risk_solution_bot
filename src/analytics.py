from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

from .kis_client import Position


@dataclass(frozen=True)
class RiskResult:
    total_asset_krw: float
    var_95_krw: float
    stress_loss_krw: float
    action_guide: str


def _download_prices(symbols: List[str], days: int = 365) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        raw = yf.download(
            symbols,
            start=start.date().isoformat(),
            end=end.date().isoformat(),
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as exc:
        print(f"[market-data] price download failed: {exc}")
        return pd.DataFrame()
    if raw.empty or "Close" not in raw:
        return pd.DataFrame()
    df = raw["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame()
    return df.dropna(how="all")


def calc_risk_metrics(positions: List[Position]) -> RiskResult:
    if not positions:
        return RiskResult(0.0, 0.0, 0.0, "보유 포지션이 없습니다.")

    symbols = sorted(set([p.symbol for p in positions]))
    weights_raw = []
    for symbol in symbols:
        symbol_val = sum(p.market_value_krw for p in positions if p.symbol == symbol)
        weights_raw.append(symbol_val)
    weights = np.array(weights_raw, dtype=float)
    total_asset = float(weights.sum())
    if total_asset <= 0:
        return RiskResult(0.0, 0.0, 0.0, "자산 평가금액이 0입니다.")
    weights = weights / total_asset

    prices = _download_prices(symbols, days=550).dropna()
    returns = prices.pct_change().dropna()
    if returns.empty or returns.shape[1] != len(symbols):
        return RiskResult(
            total_asset_krw=total_asset,
            var_95_krw=0.0,
            stress_loss_krw=total_asset * 0.11,
            action_guide="시세 데이터 부족으로 VaR 산출 생략. 외부 데이터/API 상태 확인 필요",
        )

    mu = returns.mean().to_numpy()
    cov = returns.cov().to_numpy()
    port_mean = float(np.dot(weights, mu))
    port_vol = float(np.sqrt(np.dot(weights.T, np.dot(cov, weights))))

    z = norm.ppf(0.95)
    daily_var = max(0.0, (z * port_vol - port_mean) * total_asset)
    stress_loss = total_asset * 0.11

    ratio = daily_var / total_asset if total_asset else 0.0
    if ratio >= 0.035:
        guide = "매도 비중 검토 (고위험 구간)"
    elif ratio >= 0.02:
        guide = "보유 (중립, 리밸런싱 점검)"
    else:
        guide = "추가 매수 가능 (저위험 구간)"
    return RiskResult(
        total_asset_krw=total_asset,
        var_95_krw=daily_var,
        stress_loss_krw=stress_loss,
        action_guide=guide,
    )


def calc_correlation_matrix(positions: List[Position]) -> pd.DataFrame:
    symbols = sorted(set([p.symbol for p in positions]))
    if len(symbols) < 2:
        return pd.DataFrame()
    prices = _download_prices(symbols, days=365).dropna()
    returns = prices.pct_change().dropna()
    if returns.empty:
        return pd.DataFrame()
    return returns.corr().round(3)


def build_diversification_advice(corr: pd.DataFrame) -> str:
    if corr.empty:
        return "상관관계 분석 대상 종목 수가 부족합니다."
    corr_values = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool)).stack()
    high_pairs = corr_values[corr_values >= 0.8]
    if len(high_pairs) == 0:
        return "쏠림 위험이 낮습니다. 현재 분산 상태를 유지하세요."
    top = high_pairs.sort_values(ascending=False).head(3)
    pair_txt = ", ".join([f"{a}-{b}({v:.2f})" for (a, b), v in top.items()])
    return f"상관계수가 높은 조합: {pair_txt}. 동일 섹터 비중 축소를 권장합니다."


def _roe_as_ratio(roe: float | None) -> float | None:
    if roe is None:
        return None
    value = float(roe)
    if abs(value) > 1.5:
        return value / 100.0
    return value


def _yield_as_ratio(dividend_yield: float | None) -> float:
    if dividend_yield is None:
        return 0.0
    value = float(dividend_yield)
    if value > 0.2:
        return value / 100.0
    return value


def _score_value_row(
    symbol: str,
    pe: float | None,
    pb: float | None,
    roe: float | None,
    dividend_yield: float | None,
) -> Dict[str, float | str] | None:
    roe_ratio = _roe_as_ratio(roe)
    dy_ratio = _yield_as_ratio(dividend_yield)
    if pe is None or pb is None:
        return None
    pe_value = float(pe)
    pb_value = float(pb)
    if pe_value <= 0 or pb_value <= 0:
        return None
    roe_component = max(float(roe_ratio or 0.0), 0.0)
    score = (1 / max(pe_value, 0.1)) * 35 + (1 / max(pb_value, 0.1)) * 35
    score += roe_component * 25 + dy_ratio * 5
    return {
        "symbol": symbol,
        "per": pe_value,
        "pbr": pb_value,
        "roe": float(roe_ratio or 0.0),
        "dividend_yield": dy_ratio,
        "score": float(score),
    }


def rank_value_rows(rows: List[Dict[str, float | str]], top_n: int = 5) -> List[Dict[str, float | str]]:
    rows.sort(key=lambda x: x["score"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows[:top_n]


def rotating_value_slice(
    rows: List[Dict[str, float | str]],
    page_size: int = 5,
    cycle_size: int = 30,
) -> List[Dict[str, float | str]]:
    if not rows:
        return []
    candidates = rows[: min(cycle_size, len(rows))]
    page_count = max(1, (len(candidates) + page_size - 1) // page_size)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    day_index = today.toordinal()
    page = day_index % page_count
    start = page * page_size
    end = start + page_size
    return candidates[start:end]


def undervalued_scan(universe: List[str], top_n: int = 5) -> List[Dict[str, float | str]]:
    rows: List[Dict[str, float | str]] = []
    for symbol in universe:
        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:
            print(f"[market-data] fundamentals failed for {symbol}: {exc}")
            continue
        row = _score_value_row(
            symbol=symbol,
            pe=info.get("trailingPE") or info.get("forwardPE"),
            pb=info.get("priceToBook"),
            roe=info.get("returnOnEquity"),
            dividend_yield=info.get("dividendYield"),
        )
        if row:
            rows.append(row)
    return rank_value_rows(rows, top_n=top_n)


def format_picks_for_slack(picks: List[Dict[str, float | str]], empty_label: str) -> str:
    if not picks:
        return empty_label
    lines: List[str] = []
    for p in picks:
        roe_pct = float(p["roe"]) * 100.0
        dy_pct = float(p["dividend_yield"]) * 100.0
        rank = p.get("rank")
        rank_label = f"#{int(rank)} " if rank is not None else ""
        lines.append(
            f"- {rank_label}`{p['symbol']}` PER {float(p['per']):.1f} | PBR {float(p['pbr']):.2f} | "
            f"ROE {roe_pct:.1f}% | 배당 {dy_pct:.2f}% | 점수 {float(p['score']):.1f}"
        )
    return "\n".join(lines)


def fx_fairness_analysis() -> Dict[str, float | str]:
    empty_result = {
        "current": 0.0,
        "ma20": 0.0,
        "ma120": 0.0,
        "mean_1y": 0.0,
        "view": "환율 데이터를 가져오지 못했습니다.",
    }
    try:
        raw = yf.download("KRW=X", period="1y", interval="1d", progress=False)
    except Exception as exc:
        print(f"[market-data] FX download failed: {exc}")
        return empty_result
    if raw.empty or "Close" not in raw:
        return empty_result

    usdkrw = raw["Close"].dropna()
    if isinstance(usdkrw, pd.DataFrame):
        usdkrw = usdkrw.iloc[:, 0]
    if usdkrw.empty:
        return empty_result

    current = float(usdkrw.iloc[-1])
    ma20 = float(usdkrw.rolling(20).mean().iloc[-1])
    ma120 = float(usdkrw.rolling(120).mean().iloc[-1])
    avg = float(usdkrw.mean())
    if current > ma120 * 1.05:
        view = "달러 고평가 구간, 원화 보유 우선"
    elif current < ma120 * 0.95:
        view = "달러 저평가 구간, 분할 매수 고려"
    else:
        view = "중립 구간, 환헤지 비중 유지"
    return {
        "current": current,
        "ma20": ma20,
        "ma120": ma120,
        "mean_1y": avg,
        "view": view,
    }
