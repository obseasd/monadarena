"""Tests for the strategy engine (mocked LLM calls)."""
import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.strategy_engine import StrategyEngine
from agent.config import Config
from agent.opponent_model import OpponentModel
from agent.bankroll import BankrollManager


def make_mock_engine(personality: str = "balanced"):
    """Create a StrategyEngine with mocked LLM client."""
    config = Config(anthropic_api_key="test-key")
    engine = StrategyEngine(config, personality=personality)

    # Mock the Anthropic client
    mock_client = MagicMock()
    engine.client = mock_client
    return engine, mock_client


def mock_response(text: str):
    """Create a mock Anthropic response."""
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    return mock


class TestPokerDecision:
    def test_poker_fold_decision(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Weak hand, should fold.",
            "action": "fold",
            "raise_amount": 0,
            "confidence": 0.8,
            "bluff_probability": 0.0,
            "estimated_win_prob": 0.15,
        }))

        decision = engine.decide_poker_action(
            hole_cards=["2h", "7s"],
            community_cards=["Ah", "Kd", "Qc"],
            pot=0.1,
            stack=0.5,
            opp_stack=0.5,
            position="SB",
            to_call=0.05,
            round_name="flop",
        )

        assert decision["action"] == "fold"
        assert decision["confidence"] == 0.8
        assert len(engine.decision_log) == 1

    def test_poker_raise_decision(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Strong hand, should raise.",
            "action": "raise",
            "raise_amount": 0.1,
            "confidence": 0.9,
            "bluff_probability": 0.0,
            "estimated_win_prob": 0.85,
        }))

        decision = engine.decide_poker_action(
            hole_cards=["Ah", "As"],
            community_cards=[],
            pot=0.02,
            stack=0.5,
            opp_stack=0.5,
            position="BB",
            to_call=0.01,
            round_name="preflop",
        )

        assert decision["action"] == "raise"
        assert decision["raise_amount"] == 0.1

    def test_poker_with_opponent_model(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Opponent is aggressive, adapt.",
            "action": "call",
            "raise_amount": 0,
            "confidence": 0.6,
            "bluff_probability": 0.1,
            "estimated_win_prob": 0.55,
        }))

        opponent = OpponentModel(address="0xAAA")
        opponent.record_poker_action("raise")
        opponent.record_poker_action("raise")

        bankroll = BankrollManager(initial_balance=1.0)

        decision = engine.decide_poker_action(
            hole_cards=["Kh", "Qs"],
            community_cards=["Jd", "Tc", "2h"],
            pot=0.15,
            stack=0.4,
            opp_stack=0.45,
            position="SB",
            to_call=0.05,
            round_name="flop",
            opponent=opponent,
            bankroll=bankroll,
        )

        assert decision["action"] == "call"
        # Verify the LLM was called with opponent context
        call_args = client.messages.create.call_args
        assert "aggressive" in str(call_args).lower() or "Opponent" in str(call_args)

    def test_invalid_action_defaults_to_fold(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "confused",
            "action": "all_in",  # Invalid action
            "raise_amount": 0,
            "confidence": 0.5,
        }))

        decision = engine.decide_poker_action(
            hole_cards=["5h", "6s"],
            community_cards=[],
            pot=0.02,
            stack=0.5,
            opp_stack=0.5,
            position="SB",
            to_call=0.01,
            round_name="preflop",
        )

        assert decision["action"] == "fold"


class TestAuctionDecision:
    def test_auction_bid(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Fair bid based on estimated value.",
            "bid_amount": 0.02,
            "confidence": 0.7,
            "strategy": "value",
        }))

        decision = engine.decide_auction_bid(
            item_description="Rare NFT Collection",
            estimated_value=0.03,
            min_value=0.01,
            max_value=0.05,
            budget=0.5,
            num_bidders=2,
            round_num=1,
            total_rounds=5,
        )

        assert decision["bid_amount"] == 0.02
        assert decision["strategy"] == "value"

    def test_bid_clamped_to_budget(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Going big.",
            "bid_amount": 10.0,  # Way over budget
            "confidence": 0.5,
            "strategy": "aggressive",
        }))

        decision = engine.decide_auction_bid(
            item_description="Test",
            estimated_value=0.03,
            min_value=0.01,
            max_value=0.05,
            budget=0.1,
            num_bidders=2,
            round_num=1,
            total_rounds=3,
        )

        assert decision["bid_amount"] <= 0.1


class TestWagerDecision:
    def test_wager_decision(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Conservative wager.",
            "wager_amount": 0.05,
            "confidence": 0.7,
        }))

        bankroll = BankrollManager(initial_balance=1.0)

        decision = engine.decide_wager_amount(
            game_type="poker",
            opponent=None,
            bankroll=bankroll,
        )

        assert 0.001 <= decision["wager_amount"] <= bankroll.max_wager()


class TestPersonality:
    def test_personality_in_system_prompt(self):
        """Verify personality is injected into the LLM system prompt."""
        engine, client = make_mock_engine(personality="aggressive")
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Aggressive play.",
            "action": "raise",
            "raise_amount": 0.1,
            "confidence": 0.9,
            "bluff_probability": 0.3,
            "estimated_win_prob": 0.7,
        }))

        engine.decide_poker_action(
            hole_cards=["Ah", "Kh"],
            community_cards=[],
            pot=0.05,
            stack=0.5,
            opp_stack=0.5,
            position="SB",
            to_call=0.01,
            round_name="preflop",
        )

        call_args = client.messages.create.call_args
        system_prompt = call_args.kwargs.get("system", "") or str(call_args)
        assert "AGGRESSIVE" in system_prompt.upper()

    def test_no_fold_when_free_check(self):
        """When to_call is 0, fold should convert to check (call)."""
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "Want to fold but it's free.",
            "action": "fold",
            "raise_amount": 0,
            "confidence": 0.3,
            "bluff_probability": 0.0,
            "estimated_win_prob": 0.2,
        }))

        decision = engine.decide_poker_action(
            hole_cards=["2h", "3s"],
            community_cards=["Ah", "Kd", "Qc"],
            pot=0.1,
            stack=0.5,
            opp_stack=0.5,
            position="BB",
            to_call=0.0,
            round_name="flop",
        )

        assert decision["action"] == "call"  # Converted from fold to check

    def test_different_personalities_create_different_engines(self):
        eng1, _ = make_mock_engine(personality="aggressive")
        eng2, _ = make_mock_engine(personality="conservative")
        assert eng1.personality != eng2.personality


class TestDecisionLog:
    def test_log_accumulates(self):
        engine, client = make_mock_engine()
        client.messages.create.return_value = mock_response(json.dumps({
            "reasoning": "test",
            "action": "call",
            "raise_amount": 0,
            "confidence": 0.5,
            "bluff_probability": 0,
            "estimated_win_prob": 0.5,
        }))

        for _ in range(3):
            engine.decide_poker_action(
                hole_cards=["Ah", "Kh"],
                community_cards=[],
                pot=0.05,
                stack=0.5,
                opp_stack=0.5,
                position="SB",
                to_call=0.01,
                round_name="preflop",
            )

        log = engine.get_decision_log()
        assert len(log) == 3
        assert all(entry["game_type"] == "poker" for entry in log)
