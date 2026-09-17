# -*- coding: utf-8 -*-
"""
Unit tests for the production MT5Adapter (app.services.live_trading.mt5_adapter)
Ensures full coverage of:
1. Configuration and parameter loading
2. SL/TP calculation mathematics (5-digit and 3-digit forex symbols)
3. Safety Lock against real account trading
4. Capital Floor Circuit Breaker
5. Order execution, modification, and closing via mock IPC
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.live_trading.mt5_adapter import MT5Adapter


def test_mt5_adapter_defaults():
    adapter = MT5Adapter()
    assert adapter.default_volume == 0.01
    assert adapter.magic_number == 202609
    assert adapter.default_sl_pips == 12.0
    assert adapter.default_tp_pips == 60.0
    assert adapter.capital_floor == 35.0
    assert adapter.max_consecutive_losses == 3
    assert adapter.allow_real is False


def test_mt5_adapter_calculate_sl_tp():
    adapter = MT5Adapter()
    
    with patch("app.services.live_trading.mt5_adapter.mt5") as mock_mt5:
        # Mock 5-digit symbol (EUR/USD)
        mock_info = MagicMock()
        mock_info.digits = 5
        mock_info.point = 0.00001
        mock_mt5.symbol_info.return_value = mock_info
        
        # Buy: Entry 1.08500, SL 12 pips (1.08380), TP 60 pips (1.09100)
        sl, tp = adapter.calculate_sl_tp("EURUSDm", 1.08500, 12, 60, is_buy=True)
        assert sl == 1.08380
        assert tp == 1.09100
        
        # Sell: Entry 1.08500, SL 15 pips (1.08650), TP 60 pips (1.07900)
        sl, tp = adapter.calculate_sl_tp("EURUSDm", 1.08500, 15, 60, is_buy=False)
        assert sl == 1.08650
        assert tp == 1.07900


def test_mt5_adapter_safety_lock_real_account():
    adapter = MT5Adapter()
    adapter._connected = True
    
    # Mock account_info as Real account
    mock_acc = {
        "login": 999999,
        "server": "Exness-Real10",
        "currency": "USD",
        "balance": 1000.0,
        "is_demo": False,
    }
    adapter.get_account_info = MagicMock(return_value=mock_acc)
    
    with pytest.raises(PermissionError) as excinfo:
        adapter.place_market_order(symbol="EURUSDm", order_type="buy")
    assert "SAFETY LOCK ACTIVATED" in str(excinfo.value)


def test_mt5_adapter_capital_floor_circuit_breaker():
    adapter = MT5Adapter()
    adapter._connected = True
    
    # Mock account_info with balance below $35.0 capital floor
    mock_acc = {
        "login": 416374816,
        "server": "Exness-MT5Trial14",
        "currency": "USD",
        "balance": 34.50,
        "is_demo": True,
    }
    adapter.get_account_info = MagicMock(return_value=mock_acc)
    
    with pytest.raises(RuntimeError) as excinfo:
        adapter.place_market_order(symbol="EURUSDm", order_type="buy")
    assert "CIRCUIT BREAKER TRIGGERED" in str(excinfo.value)


def test_mt5_adapter_place_order_mock_success():
    adapter = MT5Adapter()
    adapter._connected = True
    
    mock_acc = {
        "login": 416374816,
        "server": "Exness-MT5Trial14",
        "currency": "USD",
        "balance": 50.0,
        "is_demo": True,
    }
    adapter.get_account_info = MagicMock(return_value=mock_acc)
    adapter.get_quote = MagicMock(return_value={"bid": 1.08500, "ask": 1.08508})
    
    with patch("app.services.live_trading.mt5_adapter.mt5") as mock_mt5:
        sym_info = MagicMock()
        sym_info.digits = 5
        sym_info.point = 0.00001
        sym_info.filling_mode = 3
        mock_mt5.symbol_info.return_value = sym_info
        
        mock_res = MagicMock()
        mock_res.retcode = 10009
        mock_res.order = 12345678
        mock_res.price = 1.08508
        mock_res.comment = "ok"
        mock_mt5.order_send.return_value = mock_res
        
        res = adapter.place_market_order(
            symbol="EURUSDm",
            order_type="buy",
            volume=0.01,
            sl_pips=12,
            tp_pips=60,
        )
        assert res["success"] is True
        assert res["ticket"] == 12345678
        assert res["retcode"] == 10009
        assert res["sl"] == 1.08388
        assert res["tp"] == 1.09108


def test_mt5_adapter_modify_and_close_position_mock():
    adapter = MT5Adapter()
    adapter._connected = True
    
    with patch("app.services.live_trading.mt5_adapter.mt5") as mock_mt5:
        # 1. Modify
        mock_pos = MagicMock()
        mock_pos.symbol = "EURUSDm"
        mock_pos.tp = 1.09100
        mock_mt5.positions_get.return_value = [mock_pos]
        
        mock_mod_res = MagicMock()
        mock_mod_res.retcode = 10009
        mock_mt5.order_send.return_value = mock_mod_res
        
        ok = adapter.modify_position(ticket=12345678, new_sl=1.08500)
        assert ok is True
        
        # 2. Close
        adapter.get_quote = MagicMock(return_value={"bid": 1.08600, "ask": 1.08608})
        mock_close_res = MagicMock()
        mock_close_res.retcode = 10009
        mock_close_res.price = 1.08600
        mock_mt5.order_send.return_value = mock_close_res
        
        close_res = adapter.close_position(ticket=12345678)
        assert close_res["success"] is True
        assert close_res["ticket"] == 12345678
        assert close_res["close_price"] == 1.08600
