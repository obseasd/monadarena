"""
Bankroll management with Kelly Criterion-inspired risk management.
"""
from dataclasses import dataclass, field


@dataclass
class BankrollManager:
    """Manages bankroll with Kelly Criterion-inspired sizing."""

    initial_balance: float
    balance: float = 0.0
    max_single_wager_pct: float = 0.10  # Max 10% of bankroll per game
    risk_level: str = "medium"  # low / medium / high
    session_pnl: float = 0.0
    games_played: int = 0
    wins: int = 0
    history: list = field(default_factory=list)

    def __post_init__(self):
        if self.balance == 0.0:
            self.balance = self.initial_balance

        # Adjust risk per level
        if self.risk_level == "low":
            self.max_single_wager_pct = 0.05
        elif self.risk_level == "high":
            self.max_single_wager_pct = 0.15

    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.5
        return self.wins / self.games_played

    def max_wager(self) -> float:
        """Maximum wager based on current bankroll."""
        return self.balance * self.max_single_wager_pct

    def min_wager(self) -> float:
        """Minimum viable wager (0.001 MON)."""
        return 0.001

    def should_play(self, wager: float, estimated_edge: float) -> tuple[bool, str]:
        """
        Determine if we should play based on Kelly Criterion.
        Returns (should_play, reason).
        """
        if wager > self.balance:
            return False, f"Wager {wager} exceeds balance {self.balance:.4f}"

        if wager > self.max_wager():
            return False, f"Wager {wager} exceeds max ({self.max_wager():.4f})"

        if wager < self.min_wager():
            return False, f"Wager {wager} below minimum {self.min_wager()}"

        if estimated_edge <= 0 and self.risk_level != "high":
            return False, f"Negative expected value (edge: {estimated_edge:.2%})"

        # Stop-loss: if we've lost more than 30% of initial bankroll
        if self.session_pnl < -(self.initial_balance * 0.30):
            return False, f"Stop-loss triggered (session P&L: {self.session_pnl:.4f})"

        return True, "OK"

    def kelly_bet_size(self, win_prob: float, odds: float = 1.0) -> float:
        """
        Calculate optimal bet size using Kelly Criterion.

        Args:
            win_prob: Estimated probability of winning (0-1)
            odds: Payout odds (1.0 = even money after fees)

        Returns:
            Optimal bet size in MON
        """
        if win_prob <= 0 or win_prob >= 1:
            return 0.0

        # Kelly formula: f* = (bp - q) / b
        # b = odds, p = win_prob, q = 1 - win_prob
        edge = win_prob * odds - (1 - win_prob)
        if edge <= 0:
            return 0.0

        kelly_fraction = edge / odds

        # Half-Kelly for safety (reduces variance)
        half_kelly = kelly_fraction * 0.5

        # Cap at max wager percentage
        capped = min(half_kelly, self.max_single_wager_pct)

        return round(self.balance * capped, 6)

    def record_result(self, wager: float, won: bool, payout: float = 0.0):
        """Record a game result."""
        self.games_played += 1

        if won:
            self.wins += 1
            profit = payout - wager
            self.balance += profit
            self.session_pnl += profit
        else:
            self.balance -= wager
            self.session_pnl -= wager

        self.history.append({
            "wager": wager,
            "won": won,
            "payout": payout,
            "balance_after": self.balance,
            "session_pnl": self.session_pnl,
        })

    def get_summary(self) -> str:
        """Get a summary of bankroll status."""
        return (
            f"Bankroll: {self.balance:.4f} MON\n"
            f"Initial: {self.initial_balance:.4f} MON\n"
            f"Session P&L: {self.session_pnl:+.4f} MON\n"
            f"Games: {self.games_played} (W: {self.wins}, L: {self.games_played - self.wins})\n"
            f"Win rate: {self.win_rate:.1%}\n"
            f"Risk level: {self.risk_level}\n"
            f"Max wager: {self.max_wager():.4f} MON\n"
        )

    def to_prompt_context(self) -> str:
        """Format for LLM context."""
        return (
            f"BANKROLL STATUS:\n"
            f"  Balance: {self.balance:.4f} MON\n"
            f"  Session P&L: {self.session_pnl:+.4f} MON\n"
            f"  Risk level: {self.risk_level}\n"
            f"  Max bet: {self.max_wager():.4f} MON\n"
            f"  Win rate: {self.win_rate:.1%} ({self.games_played} games)\n"
        )
