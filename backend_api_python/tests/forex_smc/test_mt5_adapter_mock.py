# -*- coding: utf-8 -*-
"""
Unit tests for MT5 Bridge Adapter:
1. Simulated Login Authentication (Success & Error cases)
2. Simulated Buy / Sell Order Execution (0.01 lot, SL 10-15 pips, TP 45-75 pips, Retcodes)
"""
import pytest
from unittest.mock import MagicMock

class MockMT5AccountInfo:
    def __init__(self, login=12345678, balance=50.0, equity=50.0, margin_free=50.0, leverage=1000, currency="USD"):
        self.login = login
        self.balance = balance
        self.equity = equity
        self.margin_free = margin_free
        self.leverage = leverage
        self.currency = currency

class MockMT5OrderResult:
    def __init__(self, retcode=10009, order=99887766, price=1.08500, comment="Request executed"):
        self.retcode = retcode  # 10009 = TRADE_RETCODE_DONE
        self.order = order
        self.price = price
        self.comment = comment

class MockMT5Adapter:
    """
    Lightweight Adapter simulating the MT5 Bridge logic.
    """
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_NO_MONEY = 10019
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, mt5_module=None):
        self.mt5 = mt5_module or MagicMock()
        self.is_connected = False
        self.account_info = None

    def connect(self, login, password, server):
        if not self.mt5.initialize():
            raise ConnectionError("Failed to initialize MT5 Terminal")
        
        authorized = self.mt5.login(login=login, password=password, server=server)
        if not authorized:
            err = self.mt5.last_error()
            raise PermissionError(f"MT5 Authentication Failed: {err}")
            
        self.is_connected = True
        self.account_info = self.mt5.account_info()
        return True

    def calculate_pip_price(self, symbol, current_price, pips, is_buy=True, is_tp=False):
        """
        EUR/USD 1 pip = 0.00010
        """
        pip_value = 0.00010
        price_delta = pips * pip_value
        if is_buy:
            return round(current_price + price_delta if is_tp else current_price - price_delta, 5)
        else:
            return round(current_price - price_delta if is_tp else current_price + price_delta, 5)

    def send_market_order(self, symbol, order_type, volume, sl_pips, tp_pips, current_price):
        if not self.is_connected:
            raise RuntimeError("MT5 is not connected. Login first.")
        
        if volume <= 0 or volume > 0.02:
            raise ValueError(f"Invalid volume: {volume}. Must be 0.01 micro lot for $45 portfolio.")
            
        is_buy = (order_type == self.ORDER_TYPE_BUY)
        sl_price = self.calculate_pip_price(symbol, current_price, sl_pips, is_buy=is_buy, is_tp=False)
        tp_price = self.calculate_pip_price(symbol, current_price, tp_pips, is_buy=is_buy, is_tp=True)
        
        request = {
            "action": 1,  # TRADE_ACTION_DEAL
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": current_price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 10,
            "magic": 202609,
            "comment": "QuantDinger SMC Sniper",
        }
        
        result = self.mt5.order_send(request)
        if result.retcode == self.TRADE_RETCODE_NO_MONEY:
            raise RuntimeError("Broker rejected order: Insufficient margin (TRADE_RETCODE_NO_MONEY)")
        elif result.retcode == self.TRADE_RETCODE_REQUOTE:
            raise RuntimeError("Broker requote (TRADE_RETCODE_REQUOTE)")
        elif result.retcode != self.TRADE_RETCODE_DONE:
            raise RuntimeError(f"Order failed with retcode {result.retcode}: {result.comment}")
            
        return {
            "success": True,
            "ticket": result.order,
            "fill_price": result.price,
            "sl": sl_price,
            "tp": tp_price,
            "volume": volume
        }


# ================= TESTS =================

def test_mt5_login_success():
    """Verify successful login simulation and account info sync."""
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    mock_mt5.account_info.return_value = MockMT5AccountInfo(login=888899, balance=50.0, leverage=1000)
    
    adapter = MockMT5Adapter(mock_mt5)
    result = adapter.connect(login=888899, password="demo_password", server="Exness-MT5Trial")
    
    assert result is True
    assert adapter.is_connected is True
    assert adapter.account_info.balance == 50.0
    assert adapter.account_info.currency == "USD"
    mock_mt5.login.assert_called_once_with(login=888899, password="demo_password", server="Exness-MT5Trial")

def test_mt5_login_invalid_password():
    """Verify proper error handling when login credentials fail."""
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = False
    mock_mt5.last_error.return_value = (-1, "Invalid account credentials")
    
    adapter = MockMT5Adapter(mock_mt5)
    with pytest.raises(PermissionError) as excinfo:
        adapter.connect(login=888899, password="wrong_password", server="Exness-MT5Trial")
        
    assert "MT5 Authentication Failed" in str(excinfo.value)
    assert adapter.is_connected is False

def test_mt5_login_terminal_not_installed():
    """Verify error handling when MT5 Terminal cannot be initialized."""
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = False
    
    adapter = MockMT5Adapter(mock_mt5)
    with pytest.raises(ConnectionError) as excinfo:
        adapter.connect(login=888899, password="any", server="Exness-MT5Trial")
        
    assert "Failed to initialize MT5 Terminal" in str(excinfo.value)

def test_mt5_place_buy_order_success():
    """
    Test sending a simulated 0.01 lot Buy order on EUR/USD:
    Current Price = 1.08500
    SL = 12 pips -> 1.08380
    TP = 60 pips -> 1.09100 (R:R 1:5)
    """
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    mock_mt5.account_info.return_value = MockMT5AccountInfo()
    mock_mt5.order_send.return_value = MockMT5OrderResult(retcode=10009, order=554433, price=1.08502)
    
    adapter = MockMT5Adapter(mock_mt5)
    adapter.connect(12345, "pass", "server")
    
    res = adapter.send_market_order(
        symbol="EURUSDm",
        order_type=MockMT5Adapter.ORDER_TYPE_BUY,
        volume=0.01,
        sl_pips=12,
        tp_pips=60,
        current_price=1.08500
    )
    
    assert res["success"] is True
    assert res["ticket"] == 554433
    assert res["sl"] == 1.08380
    assert res["tp"] == 1.09100
    assert res["volume"] == 0.01

def test_mt5_place_sell_order_success():
    """
    Test sending a simulated 0.01 lot Sell order on EUR/USD:
    Current Price = 1.08500
    SL = 15 pips -> 1.08650
    TP = 60 pips -> 1.07900
    """
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    mock_mt5.account_info.return_value = MockMT5AccountInfo()
    mock_mt5.order_send.return_value = MockMT5OrderResult(retcode=10009, order=554434, price=1.08498)
    
    adapter = MockMT5Adapter(mock_mt5)
    adapter.connect(12345, "pass", "server")
    
    res = adapter.send_market_order(
        symbol="EURUSDm",
        order_type=MockMT5Adapter.ORDER_TYPE_SELL,
        volume=0.01,
        sl_pips=15,
        tp_pips=60,
        current_price=1.08500
    )
    
    assert res["success"] is True
    assert res["ticket"] == 554434
    assert res["sl"] == 1.08650
    assert res["tp"] == 1.07900

def test_mt5_order_rejection_insufficient_margin():
    """Test safety handling when broker returns TRADE_RETCODE_NO_MONEY."""
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    mock_mt5.account_info.return_value = MockMT5AccountInfo(balance=1.00)
    mock_mt5.order_send.return_value = MockMT5OrderResult(retcode=10019, comment="No money")
    
    adapter = MockMT5Adapter(mock_mt5)
    adapter.connect(12345, "pass", "server")
    
    with pytest.raises(RuntimeError) as excinfo:
        adapter.send_market_order(
            symbol="EURUSDm",
            order_type=MockMT5Adapter.ORDER_TYPE_BUY,
            volume=0.01,
            sl_pips=15,
            tp_pips=50,
            current_price=1.08500
        )
    assert "Insufficient margin" in str(excinfo.value)
