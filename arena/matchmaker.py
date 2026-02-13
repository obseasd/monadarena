"""
Matchmaker: finds and creates matches between agents.
"""
import random
import logging
from dataclasses import dataclass

from games.base import GameType
from .manager import ArenaManager, AgentProfile

logger = logging.getLogger("monadarena.matchmaker")


class Matchmaker:
    """Finds and orchestrates matches between agents."""

    def __init__(self, arena: ArenaManager):
        self.arena = arena

    def find_opponent(self, player_addr: str, game_type: GameType) -> str | None:
        """Find a suitable opponent for the given player."""
        player = self.arena.agents.get(player_addr)
        if not player:
            return None

        candidates = []
        for addr, agent in self.arena.agents.items():
            if addr == player_addr:
                continue
            # Check if opponent can afford a reasonable wager
            if agent.bankroll.balance >= agent.bankroll.min_wager():
                candidates.append(addr)

        if not candidates:
            return None

        # Prefer opponents with similar skill (games played)
        player_games = player.bankroll.games_played

        def skill_distance(addr):
            opp_games = self.arena.agents[addr].bankroll.games_played
            return abs(player_games - opp_games)

        candidates.sort(key=skill_distance)
        return candidates[0]

    def auto_match(
        self,
        game_type: GameType,
        num_matches: int = 5,
        wager: float = 0.01,
    ) -> list:
        """
        Automatically run matches between all available agents.

        Returns list of GameResults.
        """
        agents = list(self.arena.agents.keys())
        if len(agents) < 2:
            raise ValueError("Need at least 2 agents for auto-matching")

        results = []
        for i in range(num_matches):
            # Rotate matchups to ensure variety
            a_idx = i % len(agents)
            b_idx = (i + 1) % len(agents)
            if a_idx == b_idx:
                b_idx = (b_idx + 1) % len(agents)

            player_a = agents[a_idx]
            player_b = agents[b_idx]

            try:
                result = self.arena.run_match(player_a, player_b, game_type, wager)
                results.append(result)
            except Exception as e:
                logger.error(f"Match {i+1} failed: {e}")
                continue

        return results

    def round_robin(
        self,
        game_type: GameType,
        wager: float = 0.01,
    ) -> list:
        """
        Run a round-robin where every agent plays every other agent.
        Returns list of GameResults.
        """
        agents = list(self.arena.agents.keys())
        results = []

        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                try:
                    result = self.arena.run_match(agents[i], agents[j], game_type, wager)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Match failed ({agents[i][:8]} vs {agents[j][:8]}): {e}")

        return results
