"""
MonadArena CLI - Command-line interface for the AI Gaming Arena.
"""
import sys
import os
import logging
import json
import click

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.config import Config
from agent.game_client import GameClient
from arena.manager import ArenaManager
from arena.tournament import TournamentManager
from arena.matchmaker import Matchmaker
from games.base import GameType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
@click.option("--on-chain/--off-chain", default=False, help="Enable on-chain settlement")
@click.pass_context
def cli(ctx, on_chain):
    """MonadArena - AI Gaming Arena on Monad"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config()
    ctx.obj["on_chain"] = on_chain


@cli.command()
@click.pass_context
def status(ctx):
    """Show arena status and wallet balance."""
    config = ctx.obj["config"]
    print("MonadArena Status")
    print("=" * 40)
    print(f"RPC: {config.rpc_url}")
    print(f"Chain ID: {config.chain_id}")
    print(f"Arena Contract: {config.game_arena_address or 'Not deployed'}")
    print(f"Tournament Contract: {config.tournament_address or 'Not deployed'}")

    errors = config.validate()
    if errors:
        print(f"\nWarnings: {', '.join(errors)}")

    if config.private_key and config.private_key != "0x...":
        try:
            client = GameClient(config)
            balance = client.get_balance()
            print(f"\nWallet: {client.address}")
            print(f"Balance: {balance:.4f} MON")
            if config.game_arena_address and config.game_arena_address != "0x...":
                game_count = client.get_game_count()
                print(f"Total games on-chain: {game_count}")
        except Exception as e:
            print(f"\nConnection error: {e}")


@cli.command()
@click.option("--num-agents", default=4, help="Number of AI agents")
@click.option("--matches", default=5, help="Number of matches")
@click.option("--game", type=click.Choice(["poker", "auction"]), default="poker")
@click.option("--wager", default=0.05, help="Wager per match in MON")
@click.pass_context
def play(ctx, num_agents, matches, game, wager):
    """Run AI vs AI matches."""
    config = ctx.obj["config"]
    on_chain = ctx.obj["on_chain"]

    arena = ArenaManager(config, on_chain=on_chain)

    # Create agents
    addresses = [f"0x{'1' * 39}{i}" for i in range(num_agents)]
    names = ["AlphaBot", "BetaBot", "GammaBot", "DeltaBot", "EpsilonBot"]
    personalities = ["aggressive", "conservative", "balanced", "adaptive", "aggressive"]

    for i in range(min(num_agents, len(addresses))):
        arena.create_agent(
            name=names[i % len(names)],
            address=addresses[i],
            personality=personalities[i % len(personalities)],
            initial_balance=1.0,
        )

    game_type = GameType.POKER if game == "poker" else GameType.AUCTION

    matchmaker = Matchmaker(arena)
    results = matchmaker.auto_match(game_type, num_matches=matches, wager=wager)

    print(f"\nCompleted {len(results)} matches")
    print("\nLeaderboard:")
    for i, r in enumerate(arena.get_leaderboard()):
        print(f"  {i+1}. {r['name']}: {r['wins']}W/{r['games']-r['wins']}L, P&L: {r['pnl']:+.4f} MON")


@cli.command()
@click.option("--players", default=4, type=click.Choice(["2", "4", "8"]))
@click.option("--game", type=click.Choice(["poker", "auction"]), default="poker")
@click.option("--entry-fee", default=0.05, help="Entry fee in MON")
@click.pass_context
def tournament(ctx, players, game, entry_fee):
    """Run a tournament."""
    config = ctx.obj["config"]
    on_chain = ctx.obj["on_chain"]
    num_players = int(players)

    arena = ArenaManager(config, on_chain=on_chain)

    addresses = [f"0x{'1' * 39}{i}" for i in range(num_players)]
    names = ["AlphaBot", "BetaBot", "GammaBot", "DeltaBot", "EpsilonBot", "ZetaBot", "EtaBot", "ThetaBot"]
    personalities = ["aggressive", "conservative", "balanced", "adaptive"]

    for i in range(num_players):
        arena.create_agent(
            name=names[i % len(names)],
            address=addresses[i],
            personality=personalities[i % len(personalities)],
            initial_balance=1.0,
        )

    game_type = GameType.POKER if game == "poker" else GameType.AUCTION

    tmgr = TournamentManager(arena)
    tmgr.create_tournament(
        name="MonadArena Championship",
        game_type=game_type,
        entry_fee=entry_fee,
        player_addresses=addresses,
    )
    tmgr.run_tournament()
    print(tmgr.get_bracket_display())


@cli.command()
@click.argument("game_id", type=int)
@click.pass_context
def game_info(ctx, game_id):
    """Get on-chain game details."""
    config = ctx.obj["config"]
    try:
        client = GameClient(config)
        game = client.get_game(game_id)
        print(json.dumps(game, indent=2, default=str))
    except Exception as e:
        print(f"Error: {e}")


@cli.command()
@click.argument("address")
@click.pass_context
def stats(ctx, address):
    """Get on-chain player stats."""
    config = ctx.obj["config"]
    try:
        client = GameClient(config)
        player_stats = client.get_player_stats(address)
        print(json.dumps(player_stats, indent=2, default=str))
    except Exception as e:
        print(f"Error: {e}")


@cli.command()
@click.pass_context
def demo(ctx):
    """Run the full interactive demo."""
    from demo import main
    main()


if __name__ == "__main__":
    cli()
