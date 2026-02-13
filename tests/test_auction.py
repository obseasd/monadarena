"""Tests for the auction game engine."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.auction import AuctionGame, AuctionRound, AUCTION_ITEMS
from games.base import GameType, GameResult


class TestAuctionGame:
    def test_game_type(self):
        game = AuctionGame()
        assert game.get_game_type() == GameType.AUCTION

    def test_play_returns_result(self):
        """Test that a game can be played to completion with random fallback."""
        game = AuctionGame(num_rounds=3)
        result = game.play(
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
            0.1,
        )
        assert isinstance(result, GameResult)
        assert result.game_type == GameType.AUCTION
        assert result.winner in [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        ]
        assert result.wager == 0.1
        assert result.rounds_played == 3

    def test_result_details(self):
        """Test that result contains expected detail fields."""
        game = AuctionGame(num_rounds=2)
        result = game.play(
            "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            0.05,
        )
        assert "rounds" in result.details
        assert "profits" in result.details
        assert len(result.details["rounds"]) == 2

    def test_custom_items(self):
        """Test with custom auction items."""
        items = [{"name": "Test Item", "min_value": 0.01, "max_value": 0.02}]
        game = AuctionGame(items=items, num_rounds=1)
        result = game.play(
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
            0.05,
        )
        assert result.details["rounds"][0]["item"] == "Test Item"

    def test_state_summary(self):
        game = AuctionGame(num_rounds=3)
        summary = game.get_state_summary()
        assert "0/3" in summary


class TestAuctionItems:
    def test_items_have_required_fields(self):
        for item in AUCTION_ITEMS:
            assert "name" in item
            assert "min_value" in item
            assert "max_value" in item
            assert item["max_value"] > item["min_value"]
