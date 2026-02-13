"""
Base game interface for MonadArena games.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class GameType(Enum):
    POKER = 0
    AUCTION = 1
    RPG_BATTLE = 2


@dataclass
class GameResult:
    """Result of a completed game."""
    game_type: GameType
    winner: str          # Address of winner
    loser: str           # Address of loser
    wager: float         # Wager amount in MON
    details: dict        # Game-specific details (hands, bids, etc.)
    rounds_played: int
    reasoning_log: list  # LLM reasoning for each decision


class GameBase(ABC):
    """Abstract base class for all games."""

    @abstractmethod
    def get_game_type(self) -> GameType:
        """Return the game type enum."""
        ...

    @abstractmethod
    def play(self, player_a: str, player_b: str, wager: float) -> GameResult:
        """
        Play a complete game between two players.

        Args:
            player_a: Address of player A
            player_b: Address of player B
            wager: Wager amount in MON

        Returns:
            GameResult with winner, details, and reasoning log
        """
        ...

    @abstractmethod
    def get_state_summary(self) -> str:
        """Return a human-readable summary of the current game state."""
        ...
