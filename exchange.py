"""
core/exchange.py — Bybit exchange client (Unified Trading Account, V5 API)
Wraps pybit for clean error handling, rate-limit back-off, and position tracking.
"""

import time
import logging
from typing import Optional
from pybit.unified_trading import HTTP

import config

log = logging.getLogger(__name__)


class BybitClient:
    def __init__(self):
        self.session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
        )
        self._leverage_set: set[str] = set()
        log.info("BybitClient initialised — testnet=%s", config.TESTNET)

    # ── Leverage ───────────────────────────────────────────────────────────────
    def ensure_leverage(self, symbol: str):
        if symbol in self._leverage_set:
            return
        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(config.LEVERAGE),
                sellLeverage=str(config.LEVERAGE),
            )
            self._leverage_set.add(symbol)
            log.info("Leverage set to %sx for %s", config.LEVERAGE, symbol)
        except Exception as e:
            log.warning("set_leverage %s: %s", symbol, e)

    # ── Market data ───────────────────────────────────────────────────────────
    def get_klines(self, symbol: str, interval: str, limit: int) -> list[dict]:
        resp = self._call(
            self.session.get_kline,
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        if not resp:
            return []
        raw = resp["result"]["list"]
        # Each entry: [startTime, open, high, low, close, volume, turnover]
        candles = []
        for r in reversed(raw):  # oldest first
            candles.append({
                "ts":     int(r[0]),
                "open":   float(r[1]),
                "high":   float(r[2]),
                "low":    float(r[3]),
                "close":  float(r[4]),
                "volume": float(r[5]),
            })
        return candles

    def get_ticker(self, symbol: str) -> Optional[dict]:
        resp = self._call(
            self.session.get_tickers,
            category="linear",
            symbol=symbol,
        )
        if not resp:
            return None
        t = resp["result"]["list"][0]
        return {
            "bid":       float(t["bid1Price"]),
            "ask":       float(t["ask1Price"]),
            "last":      float(t["lastPrice"]),
            "mark":      float(t["markPrice"]),
            "funding":   float(t["fundingRate"]),
        }

    def get_orderbook(self, symbol: str, depth: int = 5) -> Optional[dict]:
        resp = self._call(
            self.session.get_orderbook,
            category="linear",
            symbol=symbol,
            limit=depth,
        )
        if not resp:
            return None
        ob = resp["result"]
        return {
            "bids": [(float(p), float(q)) for p, q in ob["b"]],
            "asks": [(float(p), float(q)) for p, q in ob["a"]],
        }

    # ── Account ───────────────────────────────────────────────────────────────
    def get_wallet_balance(self) -> float:
        resp = self._call(
            self.session.get_wallet_balance,
            accountType="UNIFIED",
            coin="USDT",
        )
        if not resp:
            return 0.0
        coins = resp["result"]["list"][0]["coin"]
        for c in coins:
            if c["coin"] == "USDT":
                return float(c["availableToWithdraw"])
        return 0.0

    def get_positions(self) -> list[dict]:
        resp = self._call(
            self.session.get_positions,
            category="linear",
            settleCoin="USDT",
        )
        if not resp:
            return []
        positions = []
        for p in resp["result"]["list"]:
            size = float(p["size"])
            if size == 0:
                continue
            positions.append({
                "symbol":    p["symbol"],
                "side":      p["side"],          # Buy | Sell
                "size":      size,
                "entry":     float(p["avgPrice"]),
                "mark":      float(p["markPrice"]),
                "pnl":       float(p["unrealisedPnl"]),
                "sl":        float(p["stopLoss"]) if p["stopLoss"] else None,
                "tp":        float(p["takeProfit"]) if p["takeProfit"] else None,
            })
        return positions

    def get_pnl_today(self) -> float:
        resp = self._call(
            self.session.get_closed_pnl,
            category="linear",
            limit=50,
        )
        if not resp:
            return 0.0
        total = sum(float(r["closedPnl"]) for r in resp["result"]["list"])
        return total

    # ── Orders ────────────────────────────────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        side: str,          # "Buy" | "Sell"
        qty: float,
        order_type: str = "Market",
        price: float = None,
        sl: float = None,
        tp: float = None,
        reduce_only: bool = False,
    ) -> Optional[str]:
        params = dict(
            category="linear",
            symbol=symbol,
            side=side,
            orderType=order_type,
            qty=str(qty),
            timeInForce="IOC" if order_type == "Market" else "GTC",
            reduceOnly=reduce_only,
        )
        if price:
            params["price"] = str(round(price, 4))
        if sl:
            params["stopLoss"] = str(round(sl, 4))
        if tp:
            params["takeProfit"] = str(round(tp, 4))

        resp = self._call(self.session.place_order, **params)
        if not resp:
            return None
        order_id = resp["result"]["orderId"]
        log.info("ORDER %s %s %s qty=%s sl=%s tp=%s → %s",
                 order_type, side, symbol, qty, sl, tp, order_id)
        return order_id

    def cancel_all_orders(self, symbol: str):
        self._call(
            self.session.cancel_all_orders,
            category="linear",
            symbol=symbol,
        )

    def close_position(self, symbol: str, side: str, size: float) -> Optional[str]:
        close_side = "Sell" if side == "Buy" else "Buy"
        return self.place_order(
            symbol=symbol,
            side=close_side,
            qty=size,
            order_type="Market",
            reduce_only=True,
        )

    def set_trailing_stop(self, symbol: str, trailing_pct: float):
        try:
            self.session.set_trading_stop(
                category="linear",
                symbol=symbol,
                trailingStop=str(round(trailing_pct, 2)),
            )
        except Exception as e:
            log.warning("trailing stop %s: %s", symbol, e)

    # ── Internal ──────────────────────────────────────────────────────────────
    def _call(self, fn, retries=3, **kwargs):
        for attempt in range(retries):
            try:
                resp = fn(**kwargs)
                if resp.get("retCode", -1) == 0:
                    return resp
                log.warning("API non-zero retCode %s: %s", resp.get("retCode"), resp.get("retMsg"))
                return None
            except Exception as e:
                wait = 2 ** attempt
                log.error("API error (attempt %d): %s — retrying in %ds", attempt + 1, e, wait)
                time.sleep(wait)
        return None
