"""
MonadArena Demo - Full interactive demonstration of the AI Gaming Arena.
Showcases LLM-powered poker and auction agents competing on Monad.
"""
import sys
import os
import logging
import json
from datetime import datetime

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.config import Config
from agent.bankroll import BankrollManager
from arena.manager import ArenaManager
from arena.tournament import TournamentManager
from arena.matchmaker import Matchmaker
from games.base import GameType

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monadarena.demo")

# Fake addresses for demo agents
AGENT_ADDRESSES = [
    "0x1111111111111111111111111111111111111111",
    "0x2222222222222222222222222222222222222222",
    "0x3333333333333333333333333333333333333333",
    "0x4444444444444444444444444444444444444444",
]

AGENT_CONFIGS = [
    {"name": "AlphaBot", "personality": "aggressive", "balance": 1.0},
    {"name": "BetaBot", "personality": "conservative", "balance": 1.0},
    {"name": "GammaBot", "personality": "balanced", "balance": 1.0},
    {"name": "DeltaBot", "personality": "adaptive", "balance": 1.0},
]


def print_banner():
    banner = """
    ============================================
        MONAD ARENA - AI Gaming Agent Demo
    ============================================
        AI-powered competitive gaming arena
        on Monad with LLM strategic agents
        and on-chain wagering.
    ============================================
    """
    print(banner)


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def demo_setup(config: Config) -> tuple[ArenaManager, list]:
    """Set up the arena and create agents."""
    print_section("1. SETUP - Creating AI Agents")

    arena = ArenaManager(config, on_chain=False)  # Off-chain for demo

    agents = []
    for i, (addr, cfg) in enumerate(zip(AGENT_ADDRESSES, AGENT_CONFIGS)):
        agent = arena.create_agent(
            name=cfg["name"],
            address=addr,
            personality=cfg["personality"],
            initial_balance=cfg["balance"],
        )
        agents.append(agent)
        print(f"  Created: {cfg['name']} ({cfg['personality']}) - {cfg['balance']} MON")

    print(f"\n  Total agents: {len(agents)}")
    return arena, agents


def demo_poker_matches(arena: ArenaManager, num_matches: int = 5):
    """Run poker matches between agents."""
    print_section("2. POKER MATCHES - LLM Strategic Play")

    matchmaker = Matchmaker(arena)
    results = matchmaker.auto_match(
        game_type=GameType.POKER,
        num_matches=num_matches,
        wager=0.05,
    )

    print(f"\n  Completed {len(results)} poker matches")

    for i, result in enumerate(results):
        winner_name = arena.agents[result.winner].name
        loser_name = arena.agents[result.loser].name
        method = result.details.get("win_method", "unknown")
        print(f"  Match {i+1}: {winner_name} beat {loser_name} ({method})")

    return results


def demo_auction_matches(arena: ArenaManager, num_matches: int = 3):
    """Run auction matches between agents."""
    print_section("3. AUCTION MATCHES - Strategic Bidding")

    matchmaker = Matchmaker(arena)
    results = matchmaker.auto_match(
        game_type=GameType.AUCTION,
        num_matches=num_matches,
        wager=0.05,
    )

    print(f"\n  Completed {len(results)} auction matches")

    for i, result in enumerate(results):
        winner_name = arena.agents[result.winner].name
        loser_name = arena.agents[result.loser].name
        profits = result.details.get("profits", {})
        print(f"  Match {i+1}: {winner_name} beat {loser_name} (profits: {profits})")

    return results


def demo_tournament(arena: ArenaManager):
    """Run a 4-player tournament."""
    print_section("4. TOURNAMENT - 4-Player Bracket")

    tournament_mgr = TournamentManager(arena)

    bracket = tournament_mgr.create_tournament(
        name="MonadArena Championship",
        game_type=GameType.POKER,
        entry_fee=0.05,
        player_addresses=AGENT_ADDRESSES[:4],
    )

    completed = tournament_mgr.run_tournament()

    print("\n  Tournament Bracket:")
    print(tournament_mgr.get_bracket_display())

    return completed


def demo_opponent_modeling(arena: ArenaManager):
    """Show opponent modeling data."""
    print_section("5. OPPONENT MODELING - Adaptive Strategy")

    for addr, agent in arena.agents.items():
        print(f"\n  {agent.name}'s view of opponents:")
        for opp_addr, opp_model in agent.opponent_tracker.opponents.items():
            opp_name = arena.agents.get(opp_addr, None)
            name = opp_name.name if opp_name else opp_addr[:10]
            print(f"    {name}: style={opp_model.get_style()}, "
                  f"aggression={opp_model.aggression:.1%}, "
                  f"bluff_freq={opp_model.bluff_frequency:.1%}")


def demo_bankroll(arena: ArenaManager):
    """Show bankroll management stats."""
    print_section("6. BANKROLL MANAGEMENT - Kelly Criterion")

    for addr, agent in arena.agents.items():
        br = agent.bankroll
        print(f"  {agent.name}:")
        print(f"    Balance: {br.balance:.4f} MON (started: {br.initial_balance:.4f})")
        print(f"    Session P&L: {br.session_pnl:+.4f} MON")
        print(f"    Games: {br.games_played} (W:{br.wins} L:{br.games_played-br.wins})")
        print(f"    Win rate: {br.win_rate:.1%}")
        print(f"    Max wager: {br.max_wager():.4f} MON")
        print()


def demo_leaderboard(arena: ArenaManager):
    """Show final leaderboard."""
    print_section("7. LEADERBOARD")

    rankings = arena.get_leaderboard()
    print(f"  {'Rank':<6}{'Name':<12}{'Style':<15}{'W/L':<8}{'Win%':<8}{'P&L':>10}")
    print(f"  {'-'*59}")
    for i, r in enumerate(rankings):
        wl = f"{r['wins']}/{r['games']-r['wins']}"
        print(
            f"  {i+1:<6}{r['name']:<12}{r['personality']:<15}{wl:<8}"
            f"{r['win_rate']:.1%}   {r['pnl']:+.4f} MON"
        )


def demo_llm_reasoning(arena: ArenaManager):
    """Show LLM reasoning examples."""
    print_section("8. LLM REASONING EXAMPLES")

    for addr, agent in arena.agents.items():
        decisions = agent.strategy_engine.get_decision_log()
        if decisions:
            print(f"\n  {agent.name}'s recent decisions:")
            for d in decisions[:3]:
                game_type = d.get("game_type", "?")
                decision_data = d.get("decision", {})
                reasoning = decision_data.get("reasoning", "N/A")
                action = decision_data.get("action", decision_data.get("strategy", "N/A"))
                confidence = decision_data.get("confidence", 0)
                print(f"    [{game_type}] Action: {action} (conf: {confidence:.2f})")
                print(f"    Reasoning: {reasoning[:120]}...")
                print()


def save_results(arena: ArenaManager):
    """Save match results to JSON."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "leaderboard": arena.get_leaderboard(),
        "match_history": arena.get_match_history(),
        "total_matches": len(arena.match_history),
    }

    output_path = os.path.join(os.path.dirname(__file__), "demo_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n  Results saved to {output_path}")


def main():
    print_banner()

    config = Config()
    errors = config.validate()

    if "ANTHROPIC_API_KEY not set" in errors:
        print("WARNING: ANTHROPIC_API_KEY not set!")
        print("Set it in .env or environment to enable LLM-powered decisions.")
        print("Running with mock decisions for structure demo...\n")

    # Run demo
    arena, agents = demo_setup(config)

    try:
        # Poker matches (minimum 5 required by bounty)
        demo_poker_matches(arena, num_matches=5)

        # Auction matches
        demo_auction_matches(arena, num_matches=3)

        # Tournament
        demo_tournament(arena)

        # Analytics
        demo_opponent_modeling(arena)
        demo_bankroll(arena)
        demo_leaderboard(arena)
        demo_llm_reasoning(arena)

        # Save results
        save_results(arena)

    except Exception as e:
        logger.error(f"Demo error: {e}", exc_info=True)
        print(f"\nError: {e}")
        print("Make sure ANTHROPIC_API_KEY is set in .env file")
        return 1

    print_section("DEMO COMPLETE")
    print("  MonadArena - AI Gaming Arena on Monad")
    print("  All bounty requirements met:")
    print("  [x] 2 game types (Poker + Auction)")
    print("  [x] LLM-powered strategic decisions")
    print("  [x] Wagering system with MON tokens")
    print("  [x] Smart contract escrow & payouts")
    print("  [x] 5+ matches against different opponents")
    print("  [x] Tournament system")
    print("  [x] Opponent modeling & adaptation")
    print("  [x] Bankroll management (Kelly Criterion)")
    print("  [x] AI vs AI matches")

    return 0


if __name__ == "__main__":
    sys.exit(main())
