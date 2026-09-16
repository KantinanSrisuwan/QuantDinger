# -*- coding: utf-8 -*-
"""
Unit tests for SMC Mathematical Indicator Engine:
- FVG (Fair Value Gap) calculation
- Liquidity Sweep detection
- Displacement candle detection
- No Lookahead bias verification
"""
import pytest
import pandas as pd
import numpy as np

def calculate_bullish_fvg(df):
    """
    Bullish FVG: Low of candle i > High of candle i-2.
    Gap: (High[i-2], Low[i])
    """
    fvg_list = []
    for i in range(2, len(df)):
        c1_high = df.loc[i - 2, "high"]
        c3_low = df.loc[i, "low"]
        if c3_low > c1_high:
            gap_size = c3_low - c1_high
            fvg_list.append({
                "index": i,
                "type": "bullish_fvg",
                "top": c3_low,
                "bottom": c1_high,
                "gap_pips": round(gap_size / 0.00010, 2)
            })
    return fvg_list

def calculate_liquidity_sweep(df, swing_high=None, swing_low=None):
    """
    Liquidity Sweep:
    - High breaks swing_high, but Close stays below swing_high.
    """
    sweeps = []
    for i in range(len(df)):
        h = df.loc[i, "high"]
        c = df.loc[i, "close"]
        l = df.loc[i, "low"]
        
        if swing_high is not None and h > swing_high and c < swing_high:
            sweeps.append({
                "index": i,
                "type": "sweep_high",
                "wick_penetration": round((h - swing_high) / 0.00010, 2)
            })
        if swing_low is not None and l < swing_low and c > swing_low:
            sweeps.append({
                "index": i,
                "type": "sweep_low",
                "wick_penetration": round((swing_low - l) / 0.00010, 2)
            })
    return sweeps

def calculate_displacement(df, atr_threshold=1.8):
    """
    Displacement: Candle body >= atr_threshold * mean candle body.
    """
    body = (df["close"] - df["open"]).abs()
    mean_body = body.mean()
    displacements = df[body >= (atr_threshold * mean_body)].index.tolist()
    return displacements


# ================= TESTS =================

def test_bullish_fvg_detection(fvg_scenario_data):
    """Verify that a 3-candle sequence with low[2] > high[0] correctly flags FVG."""
    fvgs = calculate_bullish_fvg(fvg_scenario_data)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg["type"] == "bullish_fvg"
    assert fvg["bottom"] == 1.0820
    assert fvg["top"] == 1.0835
    assert fvg["gap_pips"] == 15.0  # (1.0835 - 1.0820) / 0.00010 = 15 pips

def test_liquidity_sweep_high(liquidity_sweep_data):
    """Verify that a wick exceeding swing high with close below detects sweep."""
    sweeps = calculate_liquidity_sweep(liquidity_sweep_data, swing_high=1.0850)
    assert len(sweeps) == 1
    sweep = sweeps[0]
    assert sweep["type"] == "sweep_high"
    assert sweep["wick_penetration"] == 8.0  # 1.0858 - 1.0850 = 8 pips

def test_displacement_candle_detection():
    """Verify displacement candle detection on large body."""
    df = pd.DataFrame([
        {"open": 1.0810, "high": 1.0815, "low": 1.0805, "close": 1.0812},  # body = 0.0002
        {"open": 1.0812, "high": 1.0816, "low": 1.0808, "close": 1.0814},  # body = 0.0002
        {"open": 1.0814, "high": 1.0860, "low": 1.0810, "close": 1.0855},  # body = 0.0041 (Displacement)
        {"open": 1.0855, "high": 1.0858, "low": 1.0850, "close": 1.0854},  # body = 0.0001
    ])
    displacements = calculate_displacement(df, atr_threshold=1.8)
    assert 2 in displacements
    assert len(displacements) == 1

def test_no_lookahead_bias(synthetic_ohlcv):
    """Ensure calculating indicators up to bar N does not alter results when new bars arrive."""
    df_half = synthetic_ohlcv.iloc[:30].copy().reset_index(drop=True)
    fvg_at_30 = calculate_bullish_fvg(df_half)
    
    df_full = synthetic_ohlcv.copy()
    fvg_at_50 = calculate_bullish_fvg(df_full)
    
    # All FVGs detected in the first 30 bars must match exactly in full dataset
    fvg_in_first_30 = [f for f in fvg_at_50 if f["index"] < 30]
    assert fvg_at_30 == fvg_in_first_30
