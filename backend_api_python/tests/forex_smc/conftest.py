# -*- coding: utf-8 -*-
"""
Shared fixtures and synthetic data generators for Forex SMC testing.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

@pytest.fixture
def synthetic_ohlcv():
    """
    Creates a basic 15-minute OHLCV DataFrame for EUR/USD.
    """
    n_bars = 50
    start_time = datetime(2026, 9, 15, 8, 0, 0)
    timestamps = [start_time + timedelta(minutes=15 * i) for i in range(n_bars)]
    
    # Base price around 1.08500
    base_price = 1.08500
    np.random.seed(42)
    changes = np.random.normal(0, 0.0003, n_bars)
    closes = base_price + np.cumsum(changes)
    
    highs = closes + np.abs(np.random.normal(0.0002, 0.0001, n_bars))
    lows = closes - np.abs(np.random.normal(0.0002, 0.0001, n_bars))
    opens = closes + np.random.normal(0, 0.00015, n_bars)
    volumes = np.random.randint(500, 2500, n_bars)
    
    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes
    })
    return df

@pytest.fixture
def fvg_scenario_data():
    """
    Constructs an explicit 3-bar Bullish Fair Value Gap (FVG):
    Bar 0: Normal bar (High = 1.0820)
    Bar 1: Large Displacement Bullish Candle (Open = 1.0822, High = 1.0870, Low = 1.0820, Close = 1.0868)
    Bar 2: Normal bar (Low = 1.0835 > Bar 0 High of 1.0820 -> FVG gap = 1.0820 to 1.0835)
    """
    df = pd.DataFrame([
        {"bar": 0, "open": 1.0805, "high": 1.0820, "low": 1.0800, "close": 1.0818, "volume": 1000},
        {"bar": 1, "open": 1.0822, "high": 1.0870, "low": 1.0820, "close": 1.0868, "volume": 3500},
        {"bar": 2, "open": 1.0865, "high": 1.0880, "low": 1.0835, "close": 1.0875, "volume": 1200},
    ])
    return df

@pytest.fixture
def liquidity_sweep_data():
    """
    Constructs a scenario with a key Swing High at 1.0850, followed by a
    Liquidity Sweep candle (High = 1.0858 > 1.0850, but Close = 1.0842 < 1.0850).
    """
    df = pd.DataFrame([
        {"bar": 0, "open": 1.0830, "high": 1.0850, "low": 1.0825, "close": 1.0845},  # Swing High
        {"bar": 1, "open": 1.0845, "high": 1.0848, "low": 1.0835, "close": 1.0838},  # Pullback
        {"bar": 2, "open": 1.0838, "high": 1.0858, "low": 1.0832, "close": 1.0842},  # Sweep bar
    ])
    return df
