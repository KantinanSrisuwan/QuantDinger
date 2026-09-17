# -*- coding: utf-8 -*-
"""
QuantDinger MT5 Adapter for Exness Forex Trading.
Provides robust IPC bridge to MetaTrader 5 Terminal:
- Account authentication and safety locks
- Market quotes and historical candlestick streaming (15M, 4H)
- Precision order execution (0.01 lot, SL 10-15 pips, TP 45-75 pips)
- Breakeven trailing stop modification
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger("quantdinger.mt5_adapter")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


class MT5Adapter:
    """
    Exness MetaTrader 5 Bridge Adapter for QuantDinger.
    """
    TIMEFRAME_MAP = {
        "1M": 1,
        "5M": 5,
        "15M": 15,
        "30M": 30,
        "1H": 16385,
        "4H": 16388,
        "1D": 16408,
    }

    # MT5 retcodes
    RETCODE_DONE = 10009
    RETCODE_REQUOTE = 10004
    RETCODE_NO_MONEY = 10019

    def __init__(self, env_path: Optional[str] = None):
        if env_path and os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            default_env = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
            )
            if os.path.exists(default_env):
                load_dotenv(default_env)

        self.account = int(os.getenv("MT5_ACCOUNT", 0) or 0)
        self.password = os.getenv("MT5_PASSWORD", "")
        self.server = os.getenv("MT5_SERVER", "Exness-MT5Trial")
        self.path = os.getenv("MT5_PATH", "")
        self.default_symbol = os.getenv("MT5_SYMBOL", "EURUSDm")
        self.default_volume = float(os.getenv("MT5_DEFAULT_VOLUME", 0.01))
        self.magic_number = int(os.getenv("MT5_MAGIC_NUMBER", 202609))
        self.allow_real = os.getenv("FOREX_ALLOW_REAL", "false").lower() in ("true", "1", "yes")
        
        self.default_sl_pips = float(os.getenv("DEFAULT_SL_PIPS", 12))
        self.default_tp_pips = float(os.getenv("DEFAULT_TP_PIPS", 60))
        self.capital_floor = float(os.getenv("CAPITAL_FLOOR", 35.0))
        self.max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", 3))

        self._connected = False

    def is_available(self) -> bool:
        return MT5_AVAILABLE

    def connect(self) -> bool:
        """
        Initializes IPC connection to MT5 Terminal and logs in.
        """
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 package is not installed.")

        init_kwargs = {}
        if self.path and os.path.exists(self.path):
            init_kwargs["path"] = self.path
        if self.account:
            init_kwargs["login"] = self.account
        if self.password:
            init_kwargs["password"] = self.password
        if self.server:
            init_kwargs["server"] = self.server

        logger.info("Initializing MT5 with server=%s, account=%s", self.server, self.account)
        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            self._connected = False
            logger.error("MT5 initialize failed: %s", err)
            raise ConnectionError(f"Failed to connect MT5: {err}")

        acc = mt5.account_info()
        if not acc:
            err = mt5.last_error()
            self._connected = False
            logger.error("Failed to retrieve account_info after login: %s", err)
            raise PermissionError(f"Failed to get account info: {err}")

        self._connected = True
        logger.info(
            "MT5 Connected! Account: %s, Server: %s, Balance: $%.2f",
            acc.login, acc.server, acc.balance
        )
        return True

    def disconnect(self) -> None:
        """Cleanly disconnects MT5 API."""
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 connection shutdown.")

    def ensure_connected(self) -> None:
        if not self._connected:
            self.connect()

    def get_account_info(self) -> Dict[str, Any]:
        """
        Returns account balance, equity, margin, leverage and demo/real status.
        """
        self.ensure_connected()
        acc = mt5.account_info()
        if not acc:
            raise RuntimeError(f"Could not get account info: {mt5.last_error()}")

        is_demo = "trial" in acc.server.lower() or "demo" in acc.server.lower()
        return {
            "login": acc.login,
            "server": acc.server,
            "currency": acc.currency,
            "balance": float(acc.balance),
            "equity": float(acc.equity),
            "margin": float(acc.margin),
            "margin_free": float(acc.margin_free),
            "margin_level": float(acc.margin_level) if acc.margin_level else 0.0,
            "leverage": int(acc.leverage),
            "trade_allowed": bool(acc.trade_allowed),
            "is_demo": is_demo,
        }

    def get_quote(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns real-time bid, ask, and spread.
        """
        self.ensure_connected()
        sym = symbol or self.default_symbol
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        sym_info = mt5.symbol_info(sym)
        if not tick or not sym_info:
            raise ValueError(f"Failed to get quote for symbol {sym}: {mt5.last_error()}")

        point = sym_info.point or 0.00001
        pip_size = point * 10 if sym_info.digits in (3, 5) else point
        spread_pips = round((tick.ask - tick.bid) / pip_size, 2)

        return {
            "symbol": sym,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "point": point,
            "pip_size": pip_size,
            "spread_points": int(sym_info.spread),
            "spread_pips": spread_pips,
            "time": pd.to_datetime(tick.time, unit="s").isoformat(),
        }

    def get_historical_rates(
        self, symbol: Optional[str] = None, timeframe: str = "15M", count: int = 100
    ) -> pd.DataFrame:
        """
        Fetches historical OHLCV bars as a clean Pandas DataFrame.
        """
        self.ensure_connected()
        sym = symbol or self.default_symbol
        mt5.symbol_select(sym, True)

        tf = self.TIMEFRAME_MAP.get(timeframe.upper())
        if tf is None:
            tf = mt5.TIMEFRAME_M15

        rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            raise RuntimeError(f"Failed to fetch rates for {sym} ({timeframe}): {err}")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"time": "timestamp", "tick_volume": "volume"}, inplace=True)
        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    def calculate_sl_tp(
        self, symbol: str, entry_price: float, sl_pips: float, tp_pips: float, is_buy: bool
    ) -> tuple[float, float]:
        """
        Calculates exact SL and TP price levels according to symbol digits.
        """
        sym_info = mt5.symbol_info(symbol)
        digits = sym_info.digits if sym_info else 5
        point = sym_info.point if sym_info else 0.00001
        pip_size = point * 10 if digits in (3, 5) else point

        if is_buy:
            sl_price = round(entry_price - (sl_pips * pip_size), digits)
            tp_price = round(entry_price + (tp_pips * pip_size), digits)
        else:
            sl_price = round(entry_price + (sl_pips * pip_size), digits)
            tp_price = round(entry_price - (tp_pips * pip_size), digits)

        return sl_price, tp_price

    def place_market_order(
        self,
        symbol: Optional[str] = None,
        order_type: str = "buy",
        volume: Optional[float] = None,
        sl_pips: Optional[float] = None,
        tp_pips: Optional[float] = None,
        comment: str = "QuantDinger SMC Sniper",
    ) -> Dict[str, Any]:
        """
        Places a market execution order (Buy or Sell) with safety checks.
        """
        self.ensure_connected()
        sym = symbol or self.default_symbol
        vol = volume or self.default_volume
        sl_p = sl_pips if sl_pips is not None else self.default_sl_pips
        tp_p = tp_pips if tp_pips is not None else self.default_tp_pips

        acc_info = self.get_account_info()

        # HARD SAFETY LOCK: Prevent accidental real money trading during development
        if not acc_info["is_demo"] and not self.allow_real:
            raise PermissionError(
                f"SAFETY LOCK ACTIVATED: Server {acc_info['server']} is a Real account. "
                "Order execution is blocked because FOREX_ALLOW_REAL is False in .env!"
            )

        # Capital Floor Circuit Breaker
        if acc_info["balance"] < self.capital_floor:
            raise RuntimeError(
                f"CIRCUIT BREAKER TRIGGERED: Balance ${acc_info['balance']:.2f} "
                f"is below Capital Floor ${self.capital_floor:.2f}. Trading frozen!"
            )

        is_buy = order_type.lower() == "buy"
        quote = self.get_quote(sym)
        current_price = quote["ask"] if is_buy else quote["bid"]
        sl_price, tp_price = self.calculate_sl_tp(sym, current_price, sl_p, tp_p, is_buy)

        mt5_order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

        # Determine filling mode
        sym_info = mt5.symbol_info(sym)
        filling = mt5.ORDER_FILLING_IOC
        if sym_info and (sym_info.filling_mode & 1):
            filling = mt5.ORDER_FILLING_FOK
        elif sym_info and (sym_info.filling_mode & 2):
            filling = mt5.ORDER_FILLING_IOC

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": vol,
            "type": mt5_order_type,
            "price": current_price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 10,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        logger.info("Sending MT5 trade request: %s", request)
        result = mt5.order_send(request)
        if not result:
            err = mt5.last_error()
            raise RuntimeError(f"MT5 order_send returned None: {err}")

        if result.retcode == self.RETCODE_NO_MONEY:
            raise RuntimeError(f"Order rejected: Insufficient margin (retcode {result.retcode})")
        elif result.retcode == self.RETCODE_REQUOTE:
            raise RuntimeError(f"Order rejected: Requote (retcode {result.retcode})")
        elif result.retcode != self.RETCODE_DONE:
            raise RuntimeError(f"Order failed with retcode {result.retcode}: {result.comment}")

        logger.info("Order executed! Ticket: %s, Price: %s", result.order, result.price)
        return {
            "success": True,
            "ticket": int(result.order),
            "fill_price": float(result.price),
            "sl": sl_price,
            "tp": tp_price,
            "volume": vol,
            "symbol": sym,
            "order_type": order_type.lower(),
            "retcode": result.retcode,
            "comment": result.comment,
        }

    def modify_position(self, ticket: int, new_sl: float, new_tp: Optional[float] = None) -> bool:
        """
        Modifies SL / TP of an open position (used for Trailing Stop to Breakeven).
        """
        self.ensure_connected()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise ValueError(f"Position with ticket {ticket} not found.")

        pos = positions[0]
        tp_val = new_tp if new_tp is not None else pos.tp

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": float(new_sl),
            "tp": float(tp_val),
        }

        res = mt5.order_send(request)
        if not res or res.retcode != self.RETCODE_DONE:
            err = res.comment if res else mt5.last_error()
            logger.error("Failed to modify position %s: %s", ticket, err)
            return False

        logger.info("Position %s modified: SL=%.5f, TP=%.5f", ticket, new_sl, tp_val)
        return True

    def close_position(self, ticket: int) -> Dict[str, Any]:
        """
        Closes an open position at market price.
        """
        self.ensure_connected()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise ValueError(f"Position with ticket {ticket} not found.")

        pos = positions[0]
        is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
        close_order_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        quote = self.get_quote(pos.symbol)
        close_price = quote["bid"] if is_buy else quote["ask"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_order_type,
            "price": close_price,
            "deviation": 10,
            "magic": self.magic_number,
            "comment": "QuantDinger Close Position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        res = mt5.order_send(request)
        if not res or res.retcode != self.RETCODE_DONE:
            err = res.comment if res else mt5.last_error()
            raise RuntimeError(f"Failed to close position {ticket}: {err}")

        logger.info("Closed position %s at price %s", ticket, res.price)
        return {
            "success": True,
            "ticket": ticket,
            "close_price": float(res.price),
            "retcode": res.retcode,
        }

    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns list of open positions matching magic number and optional symbol.
        """
        self.ensure_connected()
        kwargs = {}
        if symbol:
            kwargs["symbol"] = symbol

        positions = mt5.positions_get(**kwargs)
        if positions is None:
            return []

        results = []
        for pos in positions:
            if pos.magic == self.magic_number:
                results.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
                    "volume": float(pos.volume),
                    "open_price": float(pos.price_open),
                    "current_price": float(pos.price_current),
                    "sl": float(pos.sl),
                    "tp": float(pos.tp),
                    "profit": float(pos.profit),
                    "time": pd.to_datetime(pos.time, unit="s").isoformat(),
                })
        return results
