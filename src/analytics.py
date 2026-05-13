from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List

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
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    df = yf.download(
        symbols,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        progress=False,
        auto_adjust=True,
    )["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame()
    return df.dropna(how="all")


def calc_risk_metrics(positions: List[Position]) -> RiskResult:
    if not positions:
        return RiskResult(0.0, 0.0, 0.0, "포지션이 없습니다.")
    symbols = sorted(set([p.symbol for p in positions]))
    prices = _download_prices(symbols, days=550).dropna()
    returns = prices.pct_change().dropna()
    weights_raw = []
    for symbol in symbols:
        symbol_val = sum(p.market_value_krw for p in positions if p.symbol == symbol)
        weights_raw.append(symbol_val)
    weights = np.array(weights_raw, dtype=float)
    total_asset = float(weights.sum())
    if total_asset <= 0:
        return RiskResult(0.0, 0.0, 0.0, "자산평가액이 0입니다.")
    weights = weights / total_asset

    mu = returns.mean().to_numpy()
    cov = returns.cov().to_numpy()
    port_mean = float(np.dot(weights, mu))
    port_vol = float(np.sqrt(np.dot(weights.T, np.dot(cov, weights))))

    alpha = 0.95
    z = norm.ppf(alpha)
    daily_var = max(0.0, (z * port_vol - port_mean) * total_asset)

    # Crisis-like one-day stress shock.
    stress_loss = total_asset * 0.11

    ratio = daily_var / total_asset if total_asset else 0.0
    if ratio >= 0.035:
        guide = "매도 비중 확대 (고위험 구간)"
    elif ratio >= 0.02:
        guide = "보유 (중립, 리밸런싱 점검)"
    else:
        guide = "추가매수 가능 (저위험 구간)"
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
    return f"상관계수 높은 조합: {pair_txt}. 동일 섹터 비중 축소를 권장합니다."


def _roe_as_ratio(roe: float | None) -> float | None:
    if roe is None:
        return None
    r = float(roe)
    if abs(r) > 1.5:
        return r / 100.0
    return r


def undervalued_scan(universe: List[str], top_n: int = 5) -> List[Dict[str, float | str]]:
    rows: List[Dict[str, float | str]] = []
    for symbol in universe:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        roe_raw = info.get("returnOnEquity")
        roe = _roe_as_ratio(roe_raw)
        dy = info.get("dividendYield")
        if pe is None or pb is None or roe is None:
            continue
        score = (1 / max(pe, 0.1)) * 30 + (1 / max(pb, 0.1)) * 25 + max(roe, 0) * 35 + (
            (dy or 0) * 10
        )
        rows.append(
            {
                "symbol": symbol,
                "per": float(pe),
                "pbr": float(pb),
                "roe": float(roe),
                "dividend_yield": float(dy or 0),
                "score": float(score),
            }
        )
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows[:top_n]


def format_picks_for_slack(picks: List[Dict[str, float | str]], empty_label: str) -> str:
    if not picks:
        return empty_label
    lines: List[str] = []
    for p in picks:
        roe = float(p["roe"])
        roe_pct = roe * 100.0 if abs(roe) <= 1.5 else roe
        dy = float(p["dividend_yield"])
        dy_pct = dy * 100.0 if dy <= 1.0 else dy
        lines.append(
            f"• `{p['symbol']}` PER {float(p['per']):.1f} | PBR {float(p['pbr']):.2f} | "
            f"ROE {roe_pct:.1f}% | 배당 {dy_pct:.2f}% | 점수 {float(p['score']):.1f}"
        )
    return "\n".join(lines)


def fx_fairness_analysis() -> Dict[str, float | str]:
    usdkrw = yf.download("KRW=X", period="1y", interval="1d", progress=False)["Close"].dropna()
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
