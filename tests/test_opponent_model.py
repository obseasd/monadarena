"""Tests for opponent modeling."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.opponent_model import OpponentModel, OpponentTracker


class TestOpponentModel:
    def test_initial_state(self):
        model = OpponentModel(address="0x123")
        assert model.games_played == 0
        assert model.aggression == 0.5
        assert model.tightness == 0.5
        assert model.bluff_frequency == 0.0
        assert model.win_rate == 0.5

    def test_record_actions(self):
        model = OpponentModel(address="0x123")
        model.record_poker_action("raise")
        model.record_poker_action("call")
        model.record_poker_action("fold")

        assert model.raise_count == 1
        assert model.call_count == 1
        assert model.fold_count == 1
        assert model.total_actions == 3

    def test_aggression(self):
        model = OpponentModel(address="0x123")
        model.record_poker_action("raise")
        model.record_poker_action("raise")
        model.record_poker_action("call")

        assert model.aggression == pytest.approx(2/3)

    def test_tightness(self):
        model = OpponentModel(address="0x123")
        model.record_poker_action("fold")
        model.record_poker_action("fold")
        model.record_poker_action("call")
        model.record_poker_action("raise")

        assert model.tightness == pytest.approx(0.5)

    def test_bluff_tracking(self):
        model = OpponentModel(address="0x123")
        model.games_played = 5
        model.record_poker_action("raise", was_bluff=True)
        model.record_poker_action("raise", was_bluff=True)
        model.record_poker_action("raise", was_bluff=False)

        assert model.bluff_count == 2
        assert model.bluff_frequency == pytest.approx(0.4)

    def test_game_results(self):
        model = OpponentModel(address="0x123")
        model.record_game_result(won=True)
        model.record_game_result(won=False)
        model.record_game_result(won=True)

        assert model.games_played == 3
        assert model.wins == 2
        assert model.losses == 1
        assert model.win_rate == pytest.approx(2/3)

    def test_style_classification(self):
        # Unknown (too few actions)
        model = OpponentModel(address="0x123")
        assert model.get_style() == "unknown"

        # Loose-aggressive
        model = OpponentModel(address="0x123")
        for _ in range(5):
            model.record_poker_action("raise")
        for _ in range(2):
            model.record_poker_action("call")
        assert model.get_style() == "loose-aggressive"

        # Tight-passive
        model = OpponentModel(address="0x456")
        for _ in range(5):
            model.record_poker_action("fold")
        for _ in range(2):
            model.record_poker_action("call")
        assert model.get_style() == "tight-passive"

    def test_auction_bid_tracking(self):
        model = OpponentModel(address="0x123")
        model.record_auction_bid(bid=0.03, item_value=0.02)
        model.record_auction_bid(bid=0.01, item_value=0.02)

        assert model.overbid_count == 1
        assert model.underbid_count == 1
        assert model.avg_bid_ratio == pytest.approx(1.0)

    def test_to_prompt_context(self):
        model = OpponentModel(address="0x1234567890")
        model.record_poker_action("raise")
        model.record_game_result(won=True)

        context = model.to_prompt_context()
        assert "0x12345678" in context
        assert "unknown" in context or "Style" in context

    def test_recent_moves_limit(self):
        model = OpponentModel(address="0x123")
        for i in range(15):
            model.record_poker_action("raise")

        assert len(model.recent_moves) == 10  # maxlen=10


class TestOpponentTracker:
    def test_get_or_create(self):
        tracker = OpponentTracker()
        model = tracker.get_or_create("0xABC")
        assert model.address == "0xabc"  # Lowercased

    def test_returns_same_model(self):
        tracker = OpponentTracker()
        m1 = tracker.get_or_create("0xABC")
        m1.record_poker_action("raise")
        m2 = tracker.get_or_create("0xABC")
        assert m2.raise_count == 1  # Same object

    def test_get_prompt_context(self):
        tracker = OpponentTracker()
        tracker.get_or_create("0xABC")
        ctx = tracker.get_prompt_context("0xABC")
        assert "Opponent" in ctx

    def test_get_all_context_empty(self):
        tracker = OpponentTracker()
        assert "No opponent data" in tracker.get_all_context()

    def test_get_all_context_with_data(self):
        tracker = OpponentTracker()
        tracker.get_or_create("0xAAA")
        tracker.get_or_create("0xBBB")
        ctx = tracker.get_all_context()
        assert "0xaaa" in ctx
        assert "0xbbb" in ctx
