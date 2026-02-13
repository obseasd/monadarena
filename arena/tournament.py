"""
Tournament bracket management for MonadArena.
"""
import logging
import math
from dataclasses import dataclass, field

from games.base import GameType, GameResult
from .manager import ArenaManager

logger = logging.getLogger("monadarena.tournament")


@dataclass
class TournamentMatch:
    round_num: int
    match_index: int
    player_a: str
    player_b: str
    winner: str = ""
    result: GameResult = None


@dataclass
class TournamentBracket:
    name: str
    game_type: GameType
    entry_fee: float
    players: list[str] = field(default_factory=list)
    matches: list[TournamentMatch] = field(default_factory=list)
    current_round: int = 1
    winner: str = ""
    completed: bool = False


class TournamentManager:
    """Manages bracket-based tournaments with automatic progression."""

    def __init__(self, arena: ArenaManager):
        self.arena = arena
        self.tournaments: list[TournamentBracket] = []

    def create_tournament(
        self,
        name: str,
        game_type: GameType,
        entry_fee: float,
        player_addresses: list[str],
    ) -> TournamentBracket:
        """
        Create and start a tournament.

        Args:
            name: Tournament name
            game_type: Game type for all matches
            entry_fee: Entry fee / wager per match
            player_addresses: List of player addresses (must be power of 2, 2-16)
        """
        n = len(player_addresses)
        if n < 2 or n > 16:
            raise ValueError("Need 2-16 players")
        if n & (n - 1) != 0:
            raise ValueError("Player count must be power of 2")

        for addr in player_addresses:
            if addr not in self.arena.agents:
                raise ValueError(f"Player {addr[:10]} not registered as an agent")

        bracket = TournamentBracket(
            name=name,
            game_type=game_type,
            entry_fee=entry_fee,
            players=player_addresses.copy(),
        )

        # Create first round matches
        for i in range(0, n, 2):
            match = TournamentMatch(
                round_num=1,
                match_index=i // 2,
                player_a=player_addresses[i],
                player_b=player_addresses[i + 1],
            )
            bracket.matches.append(match)

        self.tournaments.append(bracket)
        total_rounds = int(math.log2(n))

        logger.info(f"Tournament '{name}' created: {n} players, {total_rounds} rounds")
        return bracket

    def run_tournament(self, tournament_index: int = -1) -> TournamentBracket:
        """
        Run a complete tournament from start to finish.
        Returns the completed bracket.
        """
        bracket = self.tournaments[tournament_index]

        total_rounds = int(math.log2(len(bracket.players)))
        logger.info(f"\n{'#'*60}")
        logger.info(f"TOURNAMENT: {bracket.name}")
        logger.info(f"Game: {bracket.game_type.name} | Players: {len(bracket.players)} | Rounds: {total_rounds}")
        logger.info(f"{'#'*60}\n")

        for round_num in range(1, total_rounds + 1):
            bracket.current_round = round_num
            round_matches = [m for m in bracket.matches if m.round_num == round_num]

            round_name = "Finals" if round_num == total_rounds else (
                "Semifinals" if round_num == total_rounds - 1 else f"Round {round_num}"
            )

            logger.info(f"\n--- {round_name} ---")

            winners = []
            for match in round_matches:
                agent_a = self.arena.agents[match.player_a]
                agent_b = self.arena.agents[match.player_b]

                logger.info(f"  {agent_a.name} vs {agent_b.name}")

                result = self.arena.run_match(
                    match.player_a,
                    match.player_b,
                    bracket.game_type,
                    bracket.entry_fee,
                )

                match.winner = result.winner
                match.result = result
                winners.append(result.winner)

                winner_name = self.arena.agents[result.winner].name
                logger.info(f"  -> {winner_name} advances!")

            # Create next round matches
            if len(winners) > 1:
                for i in range(0, len(winners), 2):
                    next_match = TournamentMatch(
                        round_num=round_num + 1,
                        match_index=i // 2,
                        player_a=winners[i],
                        player_b=winners[i + 1],
                    )
                    bracket.matches.append(next_match)
            elif len(winners) == 1:
                bracket.winner = winners[0]
                bracket.completed = True

        winner_name = self.arena.agents[bracket.winner].name
        logger.info(f"\n{'#'*60}")
        logger.info(f"TOURNAMENT WINNER: {winner_name}!")
        logger.info(f"Prize Pool: {bracket.entry_fee * len(bracket.players):.4f} MON")
        logger.info(f"{'#'*60}\n")

        # On-chain tournament settlement
        if self.arena.on_chain and self.arena.game_client:
            try:
                self._settle_tournament_on_chain(bracket)
            except Exception as e:
                logger.error(f"Tournament on-chain settlement failed: {e}")

        return bracket

    def _settle_tournament_on_chain(self, bracket: TournamentBracket):
        """Settle tournament on-chain."""
        client = self.arena.game_client

        # Create on-chain tournament
        tx_hash, t_id = client.create_tournament(
            bracket.name,
            bracket.game_type.value,
            bracket.entry_fee,
            len(bracket.players),
        )
        logger.info(f"Tournament created on-chain: ID={t_id}")

        # Register players
        for addr in bracket.players:
            client.register_tournament(t_id, bracket.entry_fee)

        # Resolve matches
        for i, match in enumerate(bracket.matches):
            if match.winner:
                client.resolve_tournament_match(t_id, i, match.winner)

        logger.info(f"Tournament settled on-chain: winner={bracket.winner[:10]}...")

    def get_bracket_display(self, tournament_index: int = -1) -> str:
        """Get a text display of the tournament bracket."""
        bracket = self.tournaments[tournament_index]
        lines = [f"Tournament: {bracket.name}", "=" * 40]

        total_rounds = int(math.log2(len(bracket.players)))

        for round_num in range(1, total_rounds + 1):
            round_matches = [m for m in bracket.matches if m.round_num == round_num]

            round_name = "Finals" if round_num == total_rounds else (
                "Semifinals" if round_num == total_rounds - 1 else f"Round {round_num}"
            )

            lines.append(f"\n{round_name}:")
            for match in round_matches:
                a_name = self.arena.agents.get(match.player_a, None)
                b_name = self.arena.agents.get(match.player_b, None)
                a_str = a_name.name if a_name else match.player_a[:10]
                b_str = b_name.name if b_name else match.player_b[:10]

                if match.winner:
                    w_name = self.arena.agents.get(match.winner, None)
                    w_str = w_name.name if w_name else match.winner[:10]
                    lines.append(f"  {a_str} vs {b_str}  ->  {w_str}")
                else:
                    lines.append(f"  {a_str} vs {b_str}  ->  (pending)")

        if bracket.winner:
            w_name = self.arena.agents.get(bracket.winner, None)
            w_str = w_name.name if w_name else bracket.winner[:10]
            lines.append(f"\nChampion: {w_str}")

        return "\n".join(lines)
