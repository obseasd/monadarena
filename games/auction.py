"""
Blind Auction game engine for MonadArena.
Players bid on items with hidden valuations - tests economic reasoning and bluffing.
"""
import random
import logging
from dataclasses import dataclass, field

from .base import GameBase, GameType, GameResult

logger = logging.getLogger("monadarena.auction")

# Auction items with value ranges
AUCTION_ITEMS = [
    {"name": "Rare NFT Collection", "min_value": 0.01, "max_value": 0.05},
    {"name": "DeFi Yield Position", "min_value": 0.005, "max_value": 0.03},
    {"name": "Governance Token Bundle", "min_value": 0.008, "max_value": 0.04},
    {"name": "Exclusive Access Pass", "min_value": 0.003, "max_value": 0.02},
    {"name": "Validator Stake Slot", "min_value": 0.015, "max_value": 0.06},
]


@dataclass
class AuctionRound:
    """A single auction round."""
    round_num: int
    item: dict
    true_value: float  # Hidden true value
    bids: dict = field(default_factory=dict)  # player -> bid amount
    winner: str = ""
    winning_bid: float = 0.0


class AuctionGame(GameBase):
    """
    Blind Auction game: multiple rounds of sealed-bid auctions.

    Each round:
    1. An item is presented with an estimated value range
    2. Each player submits a sealed bid
    3. Highest bidder wins the item
    4. Profit = true_value - bid (can be negative if overbid)
    5. After all rounds, player with highest total profit wins
    """

    def __init__(
        self,
        strategy_engines: dict = None,
        num_rounds: int = 5,
        items: list[dict] = None,
    ):
        """
        Args:
            strategy_engines: Dict mapping address -> StrategyEngine
            num_rounds: Number of auction rounds
            items: Custom items list (defaults to AUCTION_ITEMS)
        """
        self.strategy_engines = strategy_engines or {}
        self.num_rounds = num_rounds
        self.items = items or AUCTION_ITEMS
        self.rounds: list[AuctionRound] = []
        self.reasoning_log: list[dict] = []

    def get_game_type(self) -> GameType:
        return GameType.AUCTION

    def get_state_summary(self) -> str:
        completed = len([r for r in self.rounds if r.winner])
        return f"Auction: {completed}/{self.num_rounds} rounds completed"

    def play(self, player_a: str, player_b: str, wager: float) -> GameResult:
        """
        Play a complete multi-round auction game.

        Each player starts with `wager` as their budget.
        Winner is the player with the highest total profit across all rounds.
        The actual wager is settled on-chain separately.
        """
        self.rounds = []
        self.reasoning_log = []

        budgets = {player_a: wager, player_b: wager}
        profits = {player_a: 0.0, player_b: 0.0}
        bid_history: list[dict] = []

        logger.info(f"Auction: {player_a[:8]} vs {player_b[:8]}, budget={wager:.4f} MON each")

        for round_num in range(1, self.num_rounds + 1):
            # Select random item
            item = random.choice(self.items)
            true_value = random.uniform(item["min_value"], item["max_value"])

            auction_round = AuctionRound(
                round_num=round_num,
                item=item,
                true_value=true_value,
            )

            logger.info(
                f"  Round {round_num}: {item['name']} "
                f"(true value: {true_value:.4f}, range: {item['min_value']}-{item['max_value']})"
            )

            # Get bids from both players
            for player in [player_a, player_b]:
                opponent = player_b if player == player_a else player_a

                bid_decision = self._get_bid(
                    player=player,
                    opponent=opponent,
                    item=item,
                    estimated_value=(item["min_value"] + item["max_value"]) / 2,
                    budget=budgets[player],
                    round_num=round_num,
                    bid_history=[b for b in bid_history if b.get("player") == player],
                )

                bid_amount = bid_decision.get("bid_amount", 0.0)
                bid_amount = max(0.0, min(bid_amount, budgets[player]))

                auction_round.bids[player] = bid_amount

                self.reasoning_log.append({
                    "player": player,
                    "round": round_num,
                    "item": item["name"],
                    "bid": bid_amount,
                    "decision": bid_decision,
                })

            # Determine round winner
            bid_a = auction_round.bids.get(player_a, 0)
            bid_b = auction_round.bids.get(player_b, 0)

            if bid_a > bid_b:
                round_winner = player_a
            elif bid_b > bid_a:
                round_winner = player_b
            else:
                round_winner = random.choice([player_a, player_b])

            auction_round.winner = round_winner
            auction_round.winning_bid = auction_round.bids[round_winner]

            # Calculate profit
            profit = true_value - auction_round.winning_bid
            profits[round_winner] += profit
            budgets[round_winner] -= auction_round.winning_bid

            loser = player_b if round_winner == player_a else player_a

            logger.info(
                f"    Bids: {player_a[:8]}={bid_a:.4f}, {player_b[:8]}={bid_b:.4f}"
            )
            logger.info(
                f"    Winner: {round_winner[:8]} (bid={auction_round.winning_bid:.4f}, "
                f"value={true_value:.4f}, profit={profit:+.4f})"
            )

            bid_history.append({
                "round": round_num,
                "item": item["name"],
                "player": round_winner,
                "your_bid": auction_round.winning_bid,
                "winning_bid": auction_round.winning_bid,
                "true_value": true_value,
            })

            self.rounds.append(auction_round)

        # Determine overall winner by total profit
        if profits[player_a] > profits[player_b]:
            winner, loser = player_a, player_b
        elif profits[player_b] > profits[player_a]:
            winner, loser = player_b, player_a
        else:
            winner, loser = player_a, player_b

        logger.info(
            f"  Final: {player_a[:8]} profit={profits[player_a]:+.4f}, "
            f"{player_b[:8]} profit={profits[player_b]:+.4f}"
        )
        logger.info(f"  Winner: {winner[:8]}")

        return GameResult(
            game_type=GameType.AUCTION,
            winner=winner,
            loser=loser,
            wager=wager,
            details={
                "rounds": [
                    {
                        "round": r.round_num,
                        "item": r.item["name"],
                        "true_value": r.true_value,
                        "bids": {k[:10]: v for k, v in r.bids.items()},
                        "winner": r.winner[:10],
                        "winning_bid": r.winning_bid,
                    }
                    for r in self.rounds
                ],
                "profits": {k[:10]: v for k, v in profits.items()},
                "budgets_remaining": {k[:10]: v for k, v in budgets.items()},
            },
            rounds_played=self.num_rounds,
            reasoning_log=self.reasoning_log,
        )

    def _get_bid(
        self,
        player: str,
        opponent: str,
        item: dict,
        estimated_value: float,
        budget: float,
        round_num: int,
        bid_history: list[dict],
    ) -> dict:
        """Get a bid decision from the player's strategy engine."""
        engine = self.strategy_engines.get(player)
        if engine is None:
            # Fallback: bid around estimated value
            bid = random.uniform(item["min_value"] * 0.8, item["max_value"] * 0.7)
            return {"bid_amount": min(bid, budget), "confidence": 0.5, "strategy": "random"}

        from agent.opponent_model import OpponentModel
        opp_model = None
        if hasattr(engine, "_opponent_tracker"):
            opp_model = engine._opponent_tracker.get_or_create(opponent)

        bankroll = None
        if hasattr(engine, "_bankroll"):
            bankroll = engine._bankroll

        decision = engine.decide_auction_bid(
            item_description=item["name"],
            estimated_value=estimated_value,
            min_value=item["min_value"],
            max_value=item["max_value"],
            budget=budget,
            num_bidders=2,
            round_num=round_num,
            total_rounds=self.num_rounds,
            bid_history=bid_history,
            opponent=opp_model,
            bankroll=bankroll,
        )

        return decision
