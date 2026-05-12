from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import httpx

from .config import AccountConfig, Settings


@dataclass(frozen=True)
class Position:
    account_alias: str
    symbol: str
    quantity: float
    market_value_krw: float
    asset_type: str


class KisClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        url = f"{self.settings.kis_base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
        }
        with httpx.Client(timeout=20.0) as client:
            res = client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"KIS token response missing access_token: {data}")
        self._token = token
        return token

    def _base_headers(self, tr_id: str) -> Dict[str, str]:
        return {
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "content-type": "application/json; charset=utf-8",
        }

    def fetch_all_positions(self) -> List[Position]:
        if self.settings.use_mock_balance:
            return self._mock_positions()
        all_positions: List[Position] = []
        for account in self.settings.kis_accounts:
            if account.market == "domestic":
                all_positions.extend(self._fetch_domestic_positions(account))
            else:
                all_positions.extend(self._fetch_overseas_positions(account))
        return all_positions

    def _fetch_domestic_positions(self, account: AccountConfig) -> List[Position]:
        url = (
            f"{self.settings.kis_base_url}"
            "/uapi/domestic-stock/v1/trading/inquire-balance"
        )
        params = {
            "CANO": account.cano,
            "ACNT_PRDT_CD": account.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        with httpx.Client(timeout=20.0) as client:
            res = client.get(url, headers=self._base_headers("TTTC8434R"), params=params)
            res.raise_for_status()
            data = res.json()
        rows = data.get("output1", [])
        positions: List[Position] = []
        for row in rows:
            symbol = row.get("pdno")
            qty = float(row.get("hldg_qty", 0) or 0)
            market_value = float(row.get("evlu_amt", 0) or 0)
            if symbol and qty > 0:
                positions.append(
                    Position(
                        account_alias=account.alias,
                        symbol=f"{symbol}.KS",
                        quantity=qty,
                        market_value_krw=market_value,
                        asset_type="equity",
                    )
                )
        return positions

    def _fetch_overseas_positions(self, account: AccountConfig) -> List[Position]:
        url = (
            f"{self.settings.kis_base_url}"
            "/uapi/overseas-stock/v1/trading/inquire-present-balance"
        )
        params = {
            "CANO": account.cano,
            "ACNT_PRDT_CD": account.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": "840",
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00",
        }
        with httpx.Client(timeout=20.0) as client:
            res = client.get(url, headers=self._base_headers("CTRP6504R"), params=params)
            res.raise_for_status()
            data = res.json()
        rows = data.get("output1", [])
        positions: List[Position] = []
        for row in rows:
            symbol = row.get("ovrs_pdno")
            qty = float(row.get("cblc_qty13", 0) or 0)
            market_value = float(row.get("frcr_evlu_amt2", 0) or 0)
            if symbol and qty > 0:
                positions.append(
                    Position(
                        account_alias=account.alias,
                        symbol=symbol,
                        quantity=qty,
                        market_value_krw=market_value,
                        asset_type="equity",
                    )
                )
        return positions

    def _mock_positions(self) -> List[Position]:
        return [
            Position("BROKER_MAIN", "005930.KS", 20, 1700000, "equity"),
            Position("BROKER_MAIN", "000660.KS", 6, 1150000, "equity"),
            Position("ISA_MAIN", "AAPL", 4, 1200000, "equity"),
            Position("ISA_MAIN", "MSFT", 2, 900000, "equity"),
            Position("ISA_MAIN", "QQQ", 3, 1800000, "equity"),
        ]
