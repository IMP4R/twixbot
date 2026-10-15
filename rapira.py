"""Rapira market API client for USDT/RUB rate fetching."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests

logger = logging.getLogger(__name__)


class RapiraClient:
    """Minimal client for Rapira public market API."""

    def __init__(self, base_url: str = "https://api.rapira.net"):
        self.session = requests.Session()
        self.base_url = base_url

    def _refresh_cookies(self) -> None:
        """Refresh session cookies by hitting the main site."""
        try:
            self.session.get("https://rapira.net", timeout=10)
        except Exception:
            pass

    def get_latest_trades(self, symbol: str = "USDT/RUB", size: int = 10) -> dict[str, Any]:
        """Fetch latest trades for a symbol."""
        self._refresh_cookies()
        try:
            resp = self.session.post(
                f"{self.base_url}/market/latest-trade",
                data={"size": size, "symbol": symbol},
                headers={"Accept": "application/json;charset=utf-8"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Rapira API error: {e}")
            return {}

    def get_current_price(self, symbol: str = "USDT/RUB") -> Decimal | None:
        """Return the latest trade price as Decimal, or None on failure."""
        data = self.get_latest_trades(symbol, size=1)
        if data.get("code") == 0 and data.get("data"):
            trade = data["data"][0]
            price = trade.get("price")
            if price is not None:
                try:
                    return Decimal(str(price))
                except Exception:
                    pass
        return None

    def get_avg_price(self, symbol: str = "USDT/RUB", trades_count: int = 10) -> Decimal | None:
        """Return average price over the last N trades."""
        data = self.get_latest_trades(symbol, size=trades_count)
        if data.get("code") == 0 and data.get("data"):
            prices = []
            for t in data["data"]:
                p = t.get("price")
                if p is not None:
                    try:
                        prices.append(Decimal(str(p)))
                    except Exception:
                        pass
            if prices:
                return sum(prices) / len(prices)
        return None

    def get_best_buy_price(self, symbol: str = "USDT/RUB", sample_size: int = 50) -> Decimal | None:
        """Return the lowest price in recent trades (best for buying)."""
        data = self.get_latest_trades(symbol, size=sample_size)
        if data.get("code") == 0 and data.get("data"):
            prices = []
            for t in data["data"]:
                p = t.get("price")
                if p is not None:
                    try:
                        prices.append(Decimal(str(p)))
                    except Exception:
                        pass
            if prices:
                return min(prices)
        return None
