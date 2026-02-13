"""Tests for bankroll management."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.bankroll import BankrollManager


class TestBankrollManager:
    def test_initial_state(self):
        br = BankrollManager(initial_balance=1.0)
        assert br.balance == 1.0
        assert br.session_pnl == 0.0
        assert br.games_played == 0

    def test_max_wager_medium_risk(self):
        br = BankrollManager(initial_balance=1.0, risk_level="medium")
        assert br.max_wager() == 0.10

    def test_max_wager_low_risk(self):
        br = BankrollManager(initial_balance=1.0, risk_level="low")
        assert br.max_wager() == 0.05

    def test_max_wager_high_risk(self):
        br = BankrollManager(initial_balance=1.0, risk_level="high")
        assert br.max_wager() == 0.15

    def test_should_play_valid(self):
        br = BankrollManager(initial_balance=1.0)
        ok, reason = br.should_play(0.05, estimated_edge=0.1)
        assert ok is True
        assert reason == "OK"

    def test_should_play_exceeds_balance(self):
        br = BankrollManager(initial_balance=0.01)
        ok, reason = br.should_play(0.05, estimated_edge=0.1)
        assert ok is False
        assert "exceeds balance" in reason

    def test_should_play_exceeds_max(self):
        br = BankrollManager(initial_balance=1.0)
        ok, reason = br.should_play(0.20, estimated_edge=0.1)
        assert ok is False
        assert "exceeds max" in reason

    def test_should_play_negative_edge(self):
        br = BankrollManager(initial_balance=1.0, risk_level="medium")
        ok, reason = br.should_play(0.05, estimated_edge=-0.1)
        assert ok is False
        assert "Negative expected value" in reason

    def test_should_play_negative_edge_high_risk(self):
        """High risk players accept negative edge."""
        br = BankrollManager(initial_balance=1.0, risk_level="high")
        ok, reason = br.should_play(0.05, estimated_edge=-0.1)
        assert ok is True

    def test_record_win(self):
        br = BankrollManager(initial_balance=1.0)
        br.record_result(wager=0.05, won=True, payout=0.099)
        assert br.games_played == 1
        assert br.wins == 1
        assert br.balance == pytest.approx(1.049)
        assert br.session_pnl == pytest.approx(0.049)

    def test_record_loss(self):
        br = BankrollManager(initial_balance=1.0)
        br.record_result(wager=0.05, won=False)
        assert br.games_played == 1
        assert br.wins == 0
        assert br.balance == pytest.approx(0.95)
        assert br.session_pnl == pytest.approx(-0.05)

    def test_stop_loss(self):
        """Stop-loss triggers after losing 30% of initial bankroll."""
        br = BankrollManager(initial_balance=1.0)
        # Simulate losses
        for _ in range(7):
            br.record_result(wager=0.05, won=False)

        ok, reason = br.should_play(0.05, estimated_edge=0.1)
        assert ok is False
        assert "Stop-loss" in reason

    def test_kelly_bet_size_positive_edge(self):
        br = BankrollManager(initial_balance=1.0)
        bet = br.kelly_bet_size(win_prob=0.6, odds=1.0)
        assert bet > 0
        assert bet <= br.max_wager()

    def test_kelly_bet_size_no_edge(self):
        br = BankrollManager(initial_balance=1.0)
        bet = br.kelly_bet_size(win_prob=0.4, odds=1.0)
        assert bet == 0.0

    def test_kelly_bet_size_even(self):
        br = BankrollManager(initial_balance=1.0)
        bet = br.kelly_bet_size(win_prob=0.5, odds=1.0)
        assert bet == 0.0

    def test_win_rate(self):
        br = BankrollManager(initial_balance=1.0)
        br.record_result(0.05, won=True, payout=0.099)
        br.record_result(0.05, won=False)
        br.record_result(0.05, won=True, payout=0.099)
        assert br.win_rate == pytest.approx(2/3)

    def test_get_summary(self):
        br = BankrollManager(initial_balance=1.0, risk_level="medium")
        summary = br.get_summary()
        assert "1.0000 MON" in summary
        assert "medium" in summary

    def test_history_tracking(self):
        br = BankrollManager(initial_balance=1.0)
        br.record_result(0.05, won=True, payout=0.099)
        assert len(br.history) == 1
        assert br.history[0]["won"] is True
