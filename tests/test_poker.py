"""Tests for the poker game engine."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.poker import (
    Card, Deck, evaluate_hand, hand_name, _is_straight,
    HAND_RANKINGS, PokerGame,
)


class TestCard:
    def test_card_creation(self):
        c = Card("A", "h")
        assert str(c) == "Ah"
        assert c.value == 14

    def test_card_values(self):
        assert Card("2", "s").value == 2
        assert Card("T", "d").value == 10
        assert Card("K", "c").value == 13


class TestDeck:
    def test_deck_has_52_cards(self):
        d = Deck()
        assert len(d.cards) == 52

    def test_deal_removes_cards(self):
        d = Deck()
        dealt = d.deal(5)
        assert len(dealt) == 5
        assert len(d.cards) == 47

    def test_reset(self):
        d = Deck()
        d.deal(10)
        d.reset()
        assert len(d.cards) == 52


class TestHandEvaluation:
    def test_high_card(self):
        cards = [Card("2", "h"), Card("5", "d"), Card("7", "c"), Card("9", "s"), Card("J", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["high_card"]

    def test_pair(self):
        cards = [Card("A", "h"), Card("A", "d"), Card("5", "c"), Card("9", "s"), Card("J", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["pair"]

    def test_two_pair(self):
        cards = [Card("A", "h"), Card("A", "d"), Card("K", "c"), Card("K", "s"), Card("J", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["two_pair"]

    def test_three_of_a_kind(self):
        cards = [Card("A", "h"), Card("A", "d"), Card("A", "c"), Card("9", "s"), Card("J", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["three_of_a_kind"]

    def test_straight(self):
        cards = [Card("5", "h"), Card("6", "d"), Card("7", "c"), Card("8", "s"), Card("9", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["straight"]

    def test_flush(self):
        cards = [Card("2", "h"), Card("5", "h"), Card("7", "h"), Card("9", "h"), Card("J", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["flush"]

    def test_full_house(self):
        cards = [Card("A", "h"), Card("A", "d"), Card("A", "c"), Card("K", "s"), Card("K", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["full_house"]

    def test_four_of_a_kind(self):
        cards = [Card("A", "h"), Card("A", "d"), Card("A", "c"), Card("A", "s"), Card("K", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["four_of_a_kind"]

    def test_straight_flush(self):
        cards = [Card("5", "h"), Card("6", "h"), Card("7", "h"), Card("8", "h"), Card("9", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["straight_flush"]

    def test_royal_flush(self):
        cards = [Card("T", "h"), Card("J", "h"), Card("Q", "h"), Card("K", "h"), Card("A", "h")]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["royal_flush"]

    def test_hand_ranking_order(self):
        """Verify hand rankings are in correct order."""
        high_card = [Card("2", "h"), Card("5", "d"), Card("7", "c"), Card("9", "s"), Card("J", "h")]
        pair = [Card("A", "h"), Card("A", "d"), Card("5", "c"), Card("9", "s"), Card("J", "h")]
        flush = [Card("2", "h"), Card("5", "h"), Card("7", "h"), Card("9", "h"), Card("J", "h")]

        r_hc, _ = evaluate_hand(high_card)
        r_pair, _ = evaluate_hand(pair)
        r_flush, _ = evaluate_hand(flush)

        assert r_hc < r_pair < r_flush

    def test_best_5_from_7(self):
        """Test selecting best 5 cards from 7 (Texas Hold'em style)."""
        cards = [
            Card("A", "h"), Card("A", "d"),  # Hole cards
            Card("A", "c"), Card("K", "s"), Card("K", "h"),  # Flop
            Card("3", "d"),  # Turn
            Card("7", "c"),  # River
        ]
        rank, _ = evaluate_hand(cards)
        assert rank == HAND_RANKINGS["full_house"]


class TestStraight:
    def test_normal_straight(self):
        assert _is_straight([9, 8, 7, 6, 5]) is True

    def test_ace_high_straight(self):
        assert _is_straight([14, 13, 12, 11, 10]) is True

    def test_ace_low_straight(self):
        assert _is_straight([14, 5, 4, 3, 2]) is True

    def test_not_straight(self):
        assert _is_straight([14, 12, 10, 8, 6]) is False


class TestHandName:
    def test_names(self):
        assert hand_name(0) == "High Card"
        assert hand_name(1) == "Pair"
        assert hand_name(9) == "Royal Flush"
