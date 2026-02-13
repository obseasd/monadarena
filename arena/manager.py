"""
Arena Manager: orchestrates matches between AI agents with on-chain settlement.
Includes bluff detection and personality-driven agent creation.
"""
import logging
import os
from dataclasses import dataclass, field

from agent.config import Config
from agent.strategy_engine import StrategyEngine
from agent.opponent_model import OpponentTracker
from agent.bankroll import BankrollManager
from agent.game_client import GameClient
from games.base import GameType, GameResult
from games.poker import PokerGame, evaluate_hand, hand_name
from games.auction import AuctionGame
from games.rpg_battle import RPGBattleGame

logger = logging.getLogger("monadarena.arena")


@dataclass
class AgentProfile:
    """An AI agent with its own strategy, personality, and wallet."""
    name: str
    address: str
    personality: str  # aggressive, conservative, balanced, adaptive
    strategy_engine: StrategyEngine = None
    bankroll: BankrollManager = None
    opponent_tracker: OpponentTracker = field(default_factory=OpponentTracker)
    bluffs_attempted: int = 0
    bluffs_successful: int = 0


class ArenaManager:
    """
    Manages the gaming arena: creates agents, runs matches, handles on-chain settlement.
    """

    def __init__(self, config: Config, on_chain: bool = True):
        self.config = config
        self.on_chain = on_chain
        self.agents: dict[str, AgentProfile] = {}
        self.match_history: list[GameResult] = []
        self.game_client: GameClient | None = None
        self.tx_log: list[dict] = []  # On-chain transaction log

        if on_chain:
            try:
                self.game_client = GameClient(config)
                logger.info(f"On-chain mode: wallet={self.game_client.address}")
            except Exception as e:
                logger.warning(f"On-chain init failed: {e}. Running off-chain only.")
                self.on_chain = False

    def create_agent(
        self,
        name: str,
        address: str,
        personality: str = "balanced",
        initial_balance: float = 1.0,
    ) -> AgentProfile:
        """Create a new AI agent with personality-driven strategy."""
        engine = StrategyEngine(self.config, personality=personality)
        bankroll = BankrollManager(
            initial_balance=initial_balance,
            risk_level=self.config.risk_level,
        )

        agent = AgentProfile(
            name=name,
            address=address,
            personality=personality,
            strategy_engine=engine,
            bankroll=bankroll,
        )

        # Attach bankroll and tracker to engine for game access
        engine._bankroll = bankroll
        engine._opponent_tracker = agent.opponent_tracker

        self.agents[address] = agent
        logger.info(f"Agent created: {name} ({personality}) @ {address[:10]}...")
        return agent

    def run_match(
        self,
        player_a_addr: str,
        player_b_addr: str,
        game_type: GameType,
        wager: float,
        rpg_max_turns: int = None,
        event_callback=None,
    ) -> GameResult:
        """Run a match between two agents with full lifecycle."""
        agent_a = self.agents.get(player_a_addr)
        agent_b = self.agents.get(player_b_addr)

        if not agent_a or not agent_b:
            raise ValueError("Both players must be registered agents")

        # Check bankroll
        for agent in [agent_a, agent_b]:
            ok, reason = agent.bankroll.should_play(wager, estimated_edge=0.05)
            if not ok:
                logger.warning(f"{agent.name} declined: {reason}")
                raise ValueError(f"{agent.name} cannot play: {reason}")

        strategy_engines = {
            player_a_addr: agent_a.strategy_engine,
            player_b_addr: agent_b.strategy_engine,
        }

        if game_type == GameType.POKER:
            # Higher blinds = more action, more showdowns
            game = PokerGame(strategy_engines=strategy_engines, small_blind=wager * 0.05, event_callback=event_callback)
        elif game_type == GameType.AUCTION:
            game = AuctionGame(strategy_engines=strategy_engines)
        elif game_type == GameType.RPG_BATTLE:
            game = RPGBattleGame(strategy_engines=strategy_engines, max_turns=rpg_max_turns, event_callback=event_callback)
        else:
            raise ValueError(f"Unknown game type: {game_type}")

        logger.info(f"\n{'='*60}")
        logger.info(f"MATCH: {agent_a.name} ({agent_a.personality}) vs {agent_b.name} ({agent_b.personality})")
        logger.info(f"Game: {game_type.name} | Wager: {wager:.4f} MON")
        logger.info(f"{'='*60}")

        # Play the game
        result = game.play(player_a_addr, player_b_addr, wager)

        # On-chain settlement
        tx_info = None
        if self.on_chain and self.game_client:
            try:
                tx_info = self._settle_on_chain(result, game_type, wager)
                result.details["tx_info"] = tx_info
            except Exception as e:
                logger.error(f"On-chain settlement failed: {e}")

        # Update agent stats with bluff detection
        self._update_agent_stats(agent_a, agent_b, result, wager)

        # Detect bluffs
        self._detect_bluffs(agent_a, agent_b, result)

        self.match_history.append(result)

        winner_name = self.agents[result.winner].name
        loser_name = self.agents[result.loser].name
        method = result.details.get("win_method", "")
        logger.info(f"RESULT: {winner_name} WINS over {loser_name} ({method})")
        if tx_info:
            logger.info(f"On-chain: game #{tx_info['game_id']} | tx: {tx_info['resolve_tx'][:20]}...")
        logger.info(f"{'='*60}\n")

        return result

    def _settle_on_chain(self, result: GameResult, game_type: GameType, wager: float) -> dict:
        """Settle the match result on-chain. Returns tx info dict."""
        logger.info("Settling on-chain...")
        explorer = self.config.explorer_url

        # Create game
        tx_hash, game_id = self.game_client.create_game(game_type.value, wager)
        logger.info(f"  Create: {explorer}/tx/{tx_hash}")

        # Join game
        join_tx = self.game_client.join_game(game_id, wager)
        logger.info(f"  Join:   {explorer}/tx/{join_tx}")

        # Resolve
        resolve_tx = self.game_client.resolve_game(game_id, result.winner)
        logger.info(f"  Resolve:{explorer}/tx/{resolve_tx}")

        tx_info = {
            "game_id": game_id,
            "create_tx": tx_hash,
            "join_tx": join_tx,
            "resolve_tx": resolve_tx,
            "explorer_url": f"{explorer}/tx/{resolve_tx}",
        }
        self.tx_log.append(tx_info)
        return tx_info

    def _detect_bluffs(self, agent_a: AgentProfile, agent_b: AgentProfile, result: GameResult):
        """Detect bluffs: when an agent raised with high bluff_probability and won by fold."""
        if result.game_type != GameType.POKER:
            return

        win_method = result.details.get("win_method", "")

        for log_entry in result.reasoning_log:
            player = log_entry["player"]
            decision = log_entry.get("decision", {})
            action = decision.get("action", "")
            bluff_prob = decision.get("bluff_probability", 0)
            win_prob = decision.get("estimated_win_prob", 0.5)

            agent = self.agents.get(player)
            if not agent:
                continue

            # A bluff is: raising with low estimated win probability OR high self-reported bluff probability
            is_bluff = (action == "raise" and (bluff_prob > 0.3 or win_prob < 0.35))

            if is_bluff:
                agent.bluffs_attempted += 1
                # Bluff succeeded if the agent won by fold
                if win_method == "fold" and result.winner == player:
                    agent.bluffs_successful += 1
                    logger.info(f"  BLUFF DETECTED: {agent.name} bluffed successfully!")

                # Record in opponent model
                opponent_addr = agent_b.address if player == agent_a.address else agent_a.address
                opp_tracker = self.agents[opponent_addr].opponent_tracker
                opp_model = opp_tracker.get_or_create(player)
                opp_model.record_poker_action(action, was_bluff=True)

    def _update_agent_stats(
        self,
        agent_a: AgentProfile,
        agent_b: AgentProfile,
        result: GameResult,
        wager: float,
    ):
        """Update agent stats after a match."""
        payout = wager * 2 * 0.99  # After 1% fee

        if result.winner == agent_a.address:
            agent_a.bankroll.record_result(wager, won=True, payout=payout)
            agent_b.bankroll.record_result(wager, won=False)
            agent_b.opponent_tracker.get_or_create(agent_a.address).record_game_result(won=True)
            agent_a.opponent_tracker.get_or_create(agent_b.address).record_game_result(won=False)
        else:
            agent_b.bankroll.record_result(wager, won=True, payout=payout)
            agent_a.bankroll.record_result(wager, won=False)
            agent_a.opponent_tracker.get_or_create(agent_b.address).record_game_result(won=True)
            agent_b.opponent_tracker.get_or_create(agent_a.address).record_game_result(won=False)

        # Record actions for opponent modeling
        for log_entry in result.reasoning_log:
            player = log_entry["player"]
            decision = log_entry.get("decision", {})
            action = decision.get("action", "")

            if action in ("fold", "call", "raise", "check"):
                opponent_addr = agent_b.address if player == agent_a.address else agent_a.address
                opp_tracker = self.agents[opponent_addr].opponent_tracker
                opp_model = opp_tracker.get_or_create(player)
                opp_model.record_poker_action(
                    action,
                    was_bluff=decision.get("bluff_probability", 0) > 0.3,
                )

    def get_leaderboard(self) -> list[dict]:
        """Get agent rankings."""
        rankings = []
        for addr, agent in self.agents.items():
            rankings.append({
                "name": agent.name,
                "address": addr[:10] + "...",
                "full_address": addr,
                "personality": agent.personality,
                "balance": agent.bankroll.balance,
                "games": agent.bankroll.games_played,
                "wins": agent.bankroll.wins,
                "win_rate": agent.bankroll.win_rate,
                "pnl": agent.bankroll.session_pnl,
                "bluffs_attempted": agent.bluffs_attempted,
                "bluffs_successful": agent.bluffs_successful,
            })

        rankings.sort(key=lambda x: x["pnl"], reverse=True)
        return rankings

    def get_match_history(self) -> list[dict]:
        """Get formatted match history."""
        history = []
        for i, result in enumerate(self.match_history):
            winner_agent = self.agents.get(result.winner)
            loser_agent = self.agents.get(result.loser)
            winner_name = winner_agent.name if winner_agent else result.winner[:10]
            loser_name = loser_agent.name if loser_agent else result.loser[:10]

            entry = {
                "match": i + 1,
                "game_type": result.game_type.name,
                "winner": winner_name,
                "loser": loser_name,
                "wager": result.wager,
                "rounds": result.rounds_played,
                "win_method": result.details.get("win_method", ""),
                "pot": result.details.get("pot", 0),
            }

            # Add hand info for poker
            if result.game_type == GameType.POKER:
                entry["hand_a"] = result.details.get("hand_a", "")
                entry["hand_b"] = result.details.get("hand_b", "")
                entry["community"] = result.details.get("community", "")

            # Add class info for RPG
            if result.game_type == GameType.RPG_BATTLE:
                entry["class_a"] = result.details.get("class_a", "")
                entry["class_b"] = result.details.get("class_b", "")
                entry["final_hp_a"] = result.details.get("final_hp_a", 0)
                entry["final_hp_b"] = result.details.get("final_hp_b", 0)

            # Add tx info
            if "tx_info" in result.details:
                entry["tx_info"] = result.details["tx_info"]

            history.append(entry)
        return history
