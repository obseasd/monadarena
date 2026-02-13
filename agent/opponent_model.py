"""
Opponent modeling: tracks and profiles opponent behavior for adaptive strategy.
"""
from dataclasses import dataclass, field
from collections import deque


@dataclass
class OpponentModel:
    """Track and profile an opponent's behavior across games."""

    address: str
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    moves_history: list = field(default_factory=list)
    recent_moves: deque = field(default_factory=lambda: deque(maxlen=10))

    # Poker-specific
    fold_count: int = 0
    call_count: int = 0
    raise_count: int = 0
    bluff_count: int = 0
    check_count: int = 0

    # Auction-specific
    bid_history: list = field(default_factory=list)
    overbid_count: int = 0
    underbid_count: int = 0

    @property
    def total_actions(self) -> int:
        return self.fold_count + self.call_count + self.raise_count + self.check_count

    @property
    def aggression(self) -> float:
        """Aggression factor: ratio of aggressive actions (raise) to passive (call/check)."""
        total = self.total_actions
        if total == 0:
            return 0.5  # Unknown, assume neutral
        return self.raise_count / total

    @property
    def tightness(self) -> float:
        """Tightness: how often they fold."""
        total = self.total_actions
        if total == 0:
            return 0.5
        return self.fold_count / total

    @property
    def bluff_frequency(self) -> float:
        """How often they bluff (detected bluffs / games played)."""
        if self.games_played == 0:
            return 0.0
        return self.bluff_count / self.games_played

    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.5
        return self.wins / self.games_played

    @property
    def avg_bid_ratio(self) -> float:
        """Average bid as ratio of item value (for auctions)."""
        if not self.bid_history:
            return 0.5
        ratios = [b["bid"] / b["value"] for b in self.bid_history if b.get("value", 0) > 0]
        return sum(ratios) / len(ratios) if ratios else 0.5

    def record_poker_action(self, action: str, was_bluff: bool = False):
        """Record a poker action."""
        self.moves_history.append(action)
        self.recent_moves.append(action)

        if action == "fold":
            self.fold_count += 1
        elif action == "call":
            self.call_count += 1
        elif action == "raise":
            self.raise_count += 1
        elif action == "check":
            self.check_count += 1

        if was_bluff:
            self.bluff_count += 1

    def record_auction_bid(self, bid: float, item_value: float):
        """Record an auction bid."""
        self.bid_history.append({"bid": bid, "value": item_value})
        if bid > item_value:
            self.overbid_count += 1
        else:
            self.underbid_count += 1

    def record_game_result(self, won: bool):
        """Record a game outcome."""
        self.games_played += 1
        if won:
            self.wins += 1
        else:
            self.losses += 1

    def get_style(self) -> str:
        """Classify opponent play style."""
        if self.total_actions < 3:
            return "unknown"

        agg = self.aggression
        tight = self.tightness

        if agg > 0.4 and tight < 0.3:
            return "loose-aggressive"
        elif agg > 0.4 and tight >= 0.3:
            return "tight-aggressive"
        elif agg <= 0.4 and tight < 0.3:
            return "loose-passive"
        else:
            return "tight-passive"

    def to_prompt_context(self) -> str:
        """Format opponent data for LLM prompt context."""
        style = self.get_style()
        recent = list(self.recent_moves)[-5:]

        return (
            f"Opponent {self.address[:10]}...:\n"
            f"  Style: {style}\n"
            f"  Games played: {self.games_played}\n"
            f"  Win rate: {self.win_rate:.1%}\n"
            f"  Aggression: {self.aggression:.1%}\n"
            f"  Tightness: {self.tightness:.1%}\n"
            f"  Bluff frequency: {self.bluff_frequency:.1%}\n"
            f"  Recent actions: {recent}\n"
        )


class OpponentTracker:
    """Manages opponent models across all games."""

    def __init__(self):
        self.opponents: dict[str, OpponentModel] = {}

    def get_or_create(self, address: str) -> OpponentModel:
        """Get or create an opponent model."""
        addr = address.lower()
        if addr not in self.opponents:
            self.opponents[addr] = OpponentModel(address=addr)
        return self.opponents[addr]

    def get_prompt_context(self, address: str) -> str:
        """Get formatted context for an opponent."""
        model = self.get_or_create(address)
        return model.to_prompt_context()

    def get_all_context(self) -> str:
        """Get context for all known opponents."""
        if not self.opponents:
            return "No opponent data available yet."
        return "\n".join(m.to_prompt_context() for m in self.opponents.values())
