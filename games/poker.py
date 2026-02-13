"""
Texas Hold'em Poker engine for MonadArena.
Heads-up (2-player) poker with LLM-driven decisions and proper betting flow.
"""
import random
import logging
from dataclasses import dataclass, field
from itertools import combinations

from .base import GameBase, GameType, GameResult

logger = logging.getLogger("monadarena.poker")

# Card constants
SUITS = ["h", "d", "c", "s"]  # hearts, diamonds, clubs, spades
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS, 2)}

HAND_RANKINGS = {
    "high_card": 0,
    "pair": 1,
    "two_pair": 2,
    "three_of_a_kind": 3,
    "straight": 4,
    "flush": 5,
    "full_house": 6,
    "four_of_a_kind": 7,
    "straight_flush": 8,
    "royal_flush": 9,
}


@dataclass
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def value(self) -> int:
        return RANK_VALUES[self.rank]


@dataclass
class Deck:
    cards: list = field(default_factory=list)

    def __post_init__(self):
        self.reset()

    def reset(self):
        self.cards = [Card(r, s) for s in SUITS for r in RANKS]
        random.shuffle(self.cards)

    def deal(self, n: int = 1) -> list[Card]:
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt


def evaluate_hand(cards: list[Card]) -> tuple[int, list[int]]:
    """
    Evaluate the best 5-card poker hand from a list of cards.
    Returns (hand_rank, tiebreaker_values) for comparison.
    """
    if len(cards) < 5:
        values = sorted([c.value for c in cards], reverse=True)
        return (HAND_RANKINGS["high_card"], values)

    best_rank = -1
    best_tiebreak = []

    for combo in combinations(cards, 5):
        rank, tiebreak = _evaluate_five(list(combo))
        if rank > best_rank or (rank == best_rank and tiebreak > best_tiebreak):
            best_rank = rank
            best_tiebreak = tiebreak

    return (best_rank, best_tiebreak)


def _evaluate_five(cards: list[Card]) -> tuple[int, list[int]]:
    """Evaluate exactly 5 cards."""
    values = sorted([c.value for c in cards], reverse=True)
    suits = [c.suit for c in cards]

    is_flush = len(set(suits)) == 1
    is_straight = _is_straight(values)

    freq = {}
    for v in values:
        freq[v] = freq.get(v, 0) + 1

    counts = sorted(freq.values(), reverse=True)
    ranked = sorted(freq.items(), key=lambda x: (x[1], x[0]), reverse=True)
    tiebreak = [v for v, _ in ranked]

    if is_flush and is_straight:
        if values[0] == 14:
            return (HAND_RANKINGS["royal_flush"], values)
        return (HAND_RANKINGS["straight_flush"], values)

    if counts == [4, 1]:
        return (HAND_RANKINGS["four_of_a_kind"], tiebreak)
    if counts == [3, 2]:
        return (HAND_RANKINGS["full_house"], tiebreak)
    if is_flush:
        return (HAND_RANKINGS["flush"], values)
    if is_straight:
        return (HAND_RANKINGS["straight"], values)
    if counts == [3, 1, 1]:
        return (HAND_RANKINGS["three_of_a_kind"], tiebreak)
    if counts == [2, 2, 1]:
        return (HAND_RANKINGS["two_pair"], tiebreak)
    if counts == [2, 1, 1, 1]:
        return (HAND_RANKINGS["pair"], tiebreak)

    return (HAND_RANKINGS["high_card"], values)


def _is_straight(values: list[int]) -> bool:
    """Check if sorted values form a straight."""
    unique = sorted(set(values), reverse=True)
    if len(unique) < 5:
        return False
    if unique[0] - unique[4] == 4:
        return True
    if unique == [14, 5, 4, 3, 2]:
        return True
    return False


def hand_name(rank: int) -> str:
    """Get human-readable hand name."""
    for name, val in HAND_RANKINGS.items():
        if val == rank:
            return name.replace("_", " ").title()
    return "Unknown"


class PokerGame(GameBase):
    """
    Heads-up Texas Hold'em with proper betting flow.
    Higher blinds (5%/10% of stack) force more action and showdowns.
    """

    def __init__(self, strategy_engines: dict = None, small_blind: float = 0.0025):
        self.strategy_engines = strategy_engines or {}
        self.small_blind = small_blind
        self.big_blind = small_blind * 2
        self.deck = Deck()
        self.community_cards: list[Card] = []
        self.hands: dict[str, list[Card]] = {}
        self.pot = 0.0
        self.round_log: list[dict] = []
        self.reasoning_log: list[dict] = []

    def get_game_type(self) -> GameType:
        return GameType.POKER

    def get_state_summary(self) -> str:
        community = ", ".join(str(c) for c in self.community_cards) or "None"
        return f"Pot: {self.pot:.4f} MON | Community: {community}"

    def play(self, player_a: str, player_b: str, wager: float) -> GameResult:
        """Play a complete heads-up poker hand."""
        self.deck.reset()
        self.community_cards = []
        self.pot = 0.0
        self.round_log = []
        self.reasoning_log = []

        stacks = {player_a: wager, player_b: wager}

        # Deal hole cards
        self.hands = {
            player_a: self.deck.deal(2),
            player_b: self.deck.deal(2),
        }

        # Player A = Small Blind, Player B = Big Blind
        sb_player = player_a
        bb_player = player_b

        sb_amount = min(self.small_blind, stacks[sb_player])
        bb_amount = min(self.big_blind, stacks[bb_player])

        stacks[sb_player] -= sb_amount
        stacks[bb_player] -= bb_amount
        self.pot = sb_amount + bb_amount

        logger.info(f"Poker: {player_a[:8]} vs {player_b[:8]}, wager={wager:.4f} MON")
        logger.info(f"  Hands: {player_a[:8]}=[{self._hand_str(player_a)}] {player_b[:8]}=[{self._hand_str(player_b)}]")
        logger.info(f"  Blinds: SB={sb_amount:.4f} BB={bb_amount:.4f}")

        rounds = [
            ("preflop", 0),
            ("flop", 3),
            ("turn", 1),
            ("river", 1),
        ]

        folded = None
        for round_name, cards_to_deal in rounds:
            if cards_to_deal > 0:
                self.community_cards.extend(self.deck.deal(cards_to_deal))

            logger.info(f"  --- {round_name.upper()} --- board=[{self._community_str()}] pot={self.pot:.4f}")

            # Run betting round
            folded = self._run_betting_round(
                round_name, sb_player, bb_player, stacks
            )

            if folded:
                break

        # Determine winner
        if folded:
            winner = player_b if folded == player_a else player_a
            loser = folded
            win_method = "fold"
            hand_a_name = "folded" if folded == player_a else ""
            hand_b_name = "folded" if folded == player_b else ""
        else:
            # Showdown
            eval_a = evaluate_hand(self.hands[player_a] + self.community_cards)
            eval_b = evaluate_hand(self.hands[player_b] + self.community_cards)

            hand_a_name = hand_name(eval_a[0])
            hand_b_name = hand_name(eval_b[0])

            if eval_a > eval_b:
                winner, loser = player_a, player_b
            elif eval_b > eval_a:
                winner, loser = player_b, player_a
            else:
                winner, loser = player_a, player_b

            win_method = "showdown"
            logger.info(
                f"  SHOWDOWN: {player_a[:8]}=[{self._hand_str(player_a)}] {hand_a_name} "
                f"vs {player_b[:8]}=[{self._hand_str(player_b)}] {hand_b_name}"
            )

        logger.info(f"  WINNER: {winner[:8]} by {win_method}, pot={self.pot:.4f} MON")

        return GameResult(
            game_type=GameType.POKER,
            winner=winner,
            loser=loser,
            wager=wager,
            details={
                "hand_a": self._hand_str(player_a),
                "hand_b": self._hand_str(player_b),
                "hand_a_name": hand_a_name,
                "hand_b_name": hand_b_name,
                "community": self._community_str(),
                "pot": self.pot,
                "win_method": win_method,
                "rounds": self.round_log,
            },
            rounds_played=len(self.round_log),
            reasoning_log=self.reasoning_log,
        )

    def _run_betting_round(
        self, round_name: str, sb_player: str, bb_player: str, stacks: dict
    ) -> str | None:
        """
        Run a single betting round. Returns the address of the player who folded, or None.

        Betting logic:
        - Preflop: SB has to call the BB difference first, then can raise
        - Post-flop: SB acts first, both check or bet/call/raise
        - A round ends when both players have acted and bets are matched
        """
        if round_name == "preflop":
            # SB owes the difference to BB
            to_call = {sb_player: self.big_blind - self.small_blind, bb_player: 0.0}
            actors = [sb_player, bb_player]
        else:
            to_call = {sb_player: 0.0, bb_player: 0.0}
            actors = [sb_player, bb_player]

        has_acted = {sb_player: False, bb_player: False}

        for _ in range(4):  # Max 4 action rounds (bet, raise, re-raise, cap)
            for player in actors:
                opponent = bb_player if player == sb_player else sb_player

                # Skip if player already acted and no new bet to face
                if has_acted[player] and to_call.get(player, 0) <= 0:
                    continue

                if stacks[player] <= 0:
                    has_acted[player] = True
                    continue

                current_to_call = max(to_call.get(player, 0), 0)

                decision = self._get_player_decision(
                    player=player,
                    opponent=opponent,
                    round_name=round_name,
                    pot=self.pot,
                    stack=stacks[player],
                    opp_stack=stacks[opponent],
                    to_call=current_to_call,
                    position="SB" if player == sb_player else "BB",
                )

                action = decision["action"]

                self.round_log.append({
                    "round": round_name,
                    "player": player,
                    "action": action,
                    "amount": decision.get("raise_amount", 0),
                    "bluff_prob": decision.get("bluff_probability", 0),
                })

                if action == "fold":
                    logger.info(f"    {player[:8]}: FOLD")
                    return player  # Return the folder

                elif action == "raise":
                    # Call first
                    call_amt = min(current_to_call, stacks[player])
                    stacks[player] -= call_amt
                    self.pot += call_amt

                    # Then raise on top
                    raise_amt = decision.get("raise_amount", self.big_blind * 2)
                    raise_amt = max(raise_amt, self.big_blind)
                    raise_amt = min(raise_amt, stacks[player])

                    stacks[player] -= raise_amt
                    self.pot += raise_amt

                    to_call[opponent] = raise_amt
                    to_call[player] = 0
                    has_acted[player] = True

                    logger.info(f"    {player[:8]}: RAISE {raise_amt:.4f} (pot={self.pot:.4f})")

                else:  # call / check
                    call_amt = min(current_to_call, stacks[player])
                    stacks[player] -= call_amt
                    self.pot += call_amt
                    to_call[player] = 0
                    has_acted[player] = True

                    if call_amt > 0:
                        logger.info(f"    {player[:8]}: CALL {call_amt:.4f} (pot={self.pot:.4f})")
                    else:
                        logger.info(f"    {player[:8]}: CHECK")

            # Round ends when both have acted and no outstanding bets
            if (has_acted[sb_player] and has_acted[bb_player]
                    and to_call.get(sb_player, 0) <= 0
                    and to_call.get(bb_player, 0) <= 0):
                break

        return None  # No fold

    def _get_player_decision(
        self, player, opponent, round_name, pot, stack, opp_stack, to_call, position
    ) -> dict:
        """Get a decision from the player's strategy engine (LLM)."""
        engine = self.strategy_engines.get(player)
        if engine is None:
            logger.warning(f"No strategy engine for {player[:8]}, using random")
            return {"action": random.choice(["call", "raise"]), "raise_amount": self.big_blind}

        from agent.opponent_model import OpponentModel
        opp_model = None
        if hasattr(engine, "_opponent_tracker"):
            opp_model = engine._opponent_tracker.get_or_create(opponent)

        bankroll = getattr(engine, "_bankroll", None)

        hole_cards = [str(c) for c in self.hands.get(player, [])]
        community = [str(c) for c in self.community_cards]

        decision = engine.decide_poker_action(
            hole_cards=hole_cards,
            community_cards=community,
            pot=pot,
            stack=stack,
            opp_stack=opp_stack,
            position=position,
            to_call=to_call,
            round_name=round_name,
            opponent=opp_model,
            bankroll=bankroll,
        )

        self.reasoning_log.append({
            "player": player,
            "round": round_name,
            "hole_cards": hole_cards,
            "community": community,
            "decision": decision,
        })

        return decision

    def _hand_str(self, player: str) -> str:
        return ", ".join(str(c) for c in self.hands.get(player, []))

    def _community_str(self) -> str:
        return ", ".join(str(c) for c in self.community_cards) if self.community_cards else "none"
