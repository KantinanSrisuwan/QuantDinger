# -*- coding: utf-8 -*-
"""
Unit tests for Portfolio Risk Controls and Circuit Breakers:
1. Max Consecutive Losses (3 losses -> 48h Lockout)
2. Capital Floor ($35.00 -> Account Freeze)
3. Zero-Risk Pyramiding (Second order requires First order at Breakeven)
"""
import pytest
from datetime import datetime, timedelta, timezone

class CircuitBreaker:
    def __init__(self, capital_floor=35.0, max_consecutive_losses=3, lockout_hours=48):
        self.capital_floor = capital_floor
        self.max_consecutive_losses = max_consecutive_losses
        self.lockout_hours = lockout_hours
        
        self.consecutive_losses = 0
        self.lockout_until = None
        self.is_frozen = False

    def record_trade_result(self, pnl, current_time=None):
        now = current_time or datetime.now(timezone.utc)
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.lockout_until = now + timedelta(hours=self.lockout_hours)
        else:
            self.consecutive_losses = 0

    def check_balance(self, balance):
        if balance < self.capital_floor:
            self.is_frozen = True
        return not self.is_frozen

    def can_trade(self, current_time=None):
        if self.is_frozen:
            return False
        now = current_time or datetime.now(timezone.utc)
        if self.lockout_until and now < self.lockout_until:
            return False
        return True

    def can_open_second_order(self, order1_entry_price, order1_current_sl, is_buy=True):
        """
        Pyramiding Rule: Order 2 can only be opened if Order 1 SL is at least at Breakeven.
        """
        if is_buy:
            return order1_current_sl >= order1_entry_price
        else:
            return order1_current_sl <= order1_entry_price


# ================= TESTS =================

def test_three_consecutive_losses_triggers_48h_lockout():
    cb = CircuitBreaker()
    t0 = datetime(2026, 9, 16, 10, 0, 0)
    
    cb.record_trade_result(pnl=-1.20, current_time=t0)
    assert cb.can_trade(t0) is True
    
    cb.record_trade_result(pnl=-1.50, current_time=t0 + timedelta(hours=1))
    assert cb.can_trade(t0 + timedelta(hours=1)) is True
    
    # 3rd consecutive loss
    t_loss3 = t0 + timedelta(hours=2)
    cb.record_trade_result(pnl=-1.10, current_time=t_loss3)
    
    # System must be locked out now
    assert cb.can_trade(t_loss3) is False
    # Still locked out after 24 hours
    assert cb.can_trade(t_loss3 + timedelta(hours=24)) is False
    # Unlocked after 48 hours
    assert cb.can_trade(t_loss3 + timedelta(hours=49)) is True

def test_win_resets_consecutive_losses():
    cb = CircuitBreaker()
    cb.record_trade_result(pnl=-1.20)
    cb.record_trade_result(pnl=-1.10)
    assert cb.consecutive_losses == 2
    
    # Winning trade resets counter
    cb.record_trade_result(pnl=5.50)
    assert cb.consecutive_losses == 0
    assert cb.can_trade() is True

def test_capital_floor_freeze():
    """If balance drops below $35, account is frozen permanently until manual review."""
    cb = CircuitBreaker(capital_floor=35.0)
    assert cb.check_balance(36.00) is True
    assert cb.can_trade() is True
    
    # Balance drops to $34.50
    assert cb.check_balance(34.50) is False
    assert cb.can_trade() is False
    assert cb.is_frozen is True

def test_zero_risk_pyramiding_rule():
    cb = CircuitBreaker()
    entry = 1.08500
    
    # Initial SL at 1.08380 (risk exists) -> Cannot open order 2
    assert cb.can_open_second_order(entry, order1_current_sl=1.08380, is_buy=True) is False
    
    # SL moved to 1.08500 (breakeven) -> Allowed
    assert cb.can_open_second_order(entry, order1_current_sl=1.08500, is_buy=True) is True
    
    # SL trailed into profit 1.08550 -> Allowed
    assert cb.can_open_second_order(entry, order1_current_sl=1.08550, is_buy=True) is True
