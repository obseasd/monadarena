"""
MonadArena Web Frontend - Flask API + Monad-styled UI.
Run with: python -m web.app
"""
import sys
import os
import json
import logging
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, render_template, jsonify, request
from agent.config import Config
from arena.manager import ArenaManager
from games.base import GameType

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "assets"),
    static_url_path="/assets",
)
logger = logging.getLogger("monadarena.web")

# Global arena state
arena: ArenaManager | None = None
match_feed: list[dict] = []
arena_lock = threading.Lock()
is_running = False
completed_matches: list[dict] = []
tournament_state: dict | None = None

# Real-time match event streaming
match_events: list[dict] = []
match_meta: dict | None = None


def get_arena() -> ArenaManager:
    """Get or create the arena manager."""
    global arena
    if arena is None:
        config = Config()
        on_chain = config.private_key and config.private_key != ("0x" + "0" * 64)
        arena = ArenaManager(config, on_chain=on_chain)
    return arena


# --- Pages ---

@app.route("/")
def index():
    return render_template("index.html")


# --- API Endpoints ---

@app.route("/api/status")
def api_status():
    """Arena status overview."""
    mgr = get_arena()
    agents = []
    for addr, agent in mgr.agents.items():
        agents.append({
            "name": agent.name,
            "address": addr[:10] + "...",
            "full_address": addr,
            "personality": agent.personality,
            "balance": round(agent.bankroll.balance, 4),
            "games": agent.bankroll.games_played,
            "wins": agent.bankroll.wins,
            "win_rate": round(agent.bankroll.win_rate * 100, 1),
            "pnl": round(agent.bankroll.session_pnl, 4),
            "bluffs_attempted": agent.bluffs_attempted,
            "bluffs_successful": agent.bluffs_successful,
        })

    return jsonify({
        "agents": agents,
        "total_matches": len(mgr.match_history),
        "on_chain": mgr.on_chain,
        "is_running": is_running,
    })


@app.route("/api/leaderboard")
def api_leaderboard():
    """Agent leaderboard."""
    mgr = get_arena()
    return jsonify(mgr.get_leaderboard())


@app.route("/api/history")
def api_history():
    """Match history."""
    mgr = get_arena()
    return jsonify(mgr.get_match_history())


@app.route("/api/feed")
def api_feed():
    """Live match feed (most recent events)."""
    return jsonify(match_feed[-50:])


@app.route("/api/match/latest")
def api_match_latest():
    """Pop the latest completed match for spectator mode."""
    if completed_matches:
        return jsonify(completed_matches.pop(0))
    return jsonify(None)


@app.route("/api/agents/create", methods=["POST"])
def api_create_agent():
    """Create a new AI agent."""
    data = request.json
    name = data.get("name", "Agent")
    address = data.get("address", f"0x{''.join(f'{i:02x}' for i in os.urandom(20))}")
    personality = data.get("personality", "balanced")
    balance = float(data.get("balance", 1.0))

    mgr = get_arena()
    agent = mgr.create_agent(name, address, personality, balance)

    add_feed_event("agent_created", f"{name} ({personality}) joined the arena")

    return jsonify({
        "success": True,
        "agent": {
            "name": agent.name,
            "address": address[:10] + "...",
            "personality": agent.personality,
            "balance": balance,
        },
    })


@app.route("/api/match/run", methods=["POST"])
def api_run_match():
    """Run a single match between two agents."""
    global is_running
    data = request.json
    player_a = data.get("player_a")
    player_b = data.get("player_b")
    game_type = data.get("game_type", "poker")
    wager = float(data.get("wager", 0.05))

    mgr = get_arena()

    if not player_a or not player_b:
        return jsonify({"error": "Need both player_a and player_b addresses"}), 400

    type_map = {"poker": GameType.POKER, "auction": GameType.AUCTION, "rpg": GameType.RPG_BATTLE}
    gt = type_map.get(game_type, GameType.POKER)

    is_running = True
    add_feed_event("match_start", f"Match starting: {game_type.upper()} | Wager: {wager:.4f} MON")

    try:
        result = mgr.run_match(player_a, player_b, gt, wager)

        winner_name = mgr.agents[result.winner].name
        loser_name = mgr.agents[result.loser].name
        method = result.details.get("win_method", "")

        add_feed_event("match_result", (
            f"{winner_name} defeated {loser_name} by {method} | "
            f"Pot: {result.details.get('pot', 0):.4f} MON"
        ))

        # Add reasoning highlights
        for log in result.reasoning_log[-2:]:
            decision = log.get("decision", {})
            player = log["player"]
            agent_name = mgr.agents.get(player, None)
            name = agent_name.name if agent_name else player[:10]
            add_feed_event("reasoning", (
                f"{name}: {decision.get('action', '?')} "
                f"(conf={decision.get('confidence', 0):.0%}, "
                f"bluff={decision.get('bluff_probability', 0):.0%})"
            ))

        is_running = False

        # Build game-type-specific details
        details = {}
        if gt == GameType.POKER:
            details = {
                "hand_a": result.details.get("hand_a", ""),
                "hand_b": result.details.get("hand_b", ""),
                "hand_a_name": result.details.get("hand_a_name", ""),
                "hand_b_name": result.details.get("hand_b_name", ""),
                "community": result.details.get("community", ""),
                "rounds": result.details.get("rounds", []),
                "rounds_count": len(result.details.get("rounds", [])),
            }
        elif gt == GameType.RPG_BATTLE:
            details = {
                "class_a": result.details.get("class_a", ""),
                "class_b": result.details.get("class_b", ""),
                "final_hp_a": result.details.get("final_hp_a", 0),
                "final_hp_b": result.details.get("final_hp_b", 0),
                "max_hp_a": result.details.get("max_hp_a", 100),
                "max_hp_b": result.details.get("max_hp_b", 100),
                "turns": result.details.get("turns", 0),
                "turn_log": result.details.get("turn_log", []),
            }

        return jsonify({
            "success": True,
            "game_type": game_type,
            "winner": winner_name,
            "loser": loser_name,
            "winner_addr": result.winner,
            "loser_addr": result.loser,
            "player_a_addr": player_a,
            "player_b_addr": player_b,
            "method": method,
            "pot": result.details.get("pot", 0),
            "details": details,
        })

    except Exception as e:
        is_running = False
        add_feed_event("error", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/api/match/start", methods=["POST"])
def api_start_match():
    """Start a match in background with real-time event streaming."""
    global is_running, match_events, match_meta
    if is_running:
        return jsonify({"error": "A match is already running"}), 409

    data = request.json
    player_a = data.get("player_a")
    player_b = data.get("player_b")
    game_type = data.get("game_type", "poker")
    wager = float(data.get("wager", 0.05))
    num_rounds = int(data.get("rounds", 3))

    mgr = get_arena()
    if not player_a or not player_b:
        return jsonify({"error": "Need both player_a and player_b addresses"}), 400

    agent_a = mgr.agents.get(player_a)
    agent_b = mgr.agents.get(player_b)
    if not agent_a or not agent_b:
        return jsonify({"error": "Both players must be registered agents"}), 400

    # Reset event queue
    match_events = []
    match_meta = {
        "game_type": game_type,
        "player_a": player_a,
        "player_b": player_b,
        "player_a_name": agent_a.name,
        "player_b_name": agent_b.name,
        "player_a_personality": agent_a.personality,
        "player_b_personality": agent_b.personality,
        "num_rounds": num_rounds,
        "wager": wager,
        "status": "running",
    }
    is_running = True

    thread = threading.Thread(
        target=_run_streaming_match,
        args=(player_a, player_b, game_type, wager, num_rounds),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "meta": match_meta})


@app.route("/api/match/events")
def api_match_events():
    """Get match events since offset for real-time animation."""
    offset = int(request.args.get("offset", 0))
    events = match_events[offset:]
    return jsonify({
        "events": events,
        "total": len(match_events),
        "meta": match_meta,
    })


def _run_streaming_match(player_a, player_b, game_type, wager, num_rounds):
    """Run match(es) in background, pushing events in real-time via game engine callbacks."""
    global is_running, match_meta
    mgr = get_arena()
    type_map = {"poker": GameType.POKER, "auction": GameType.AUCTION, "rpg": GameType.RPG_BATTLE}
    gt = type_map.get(game_type, GameType.POKER)

    name_a = mgr.agents[player_a].name
    name_b = mgr.agents[player_b].name

    try:
        for round_idx in range(num_rounds):
            current_round = round_idx + 1

            # Emit round start
            match_events.append({
                "type": "round_start",
                "round": current_round,
                "total_rounds": num_rounds,
                "game_type": game_type,
            })
            add_feed_event("match_start",
                f"Round {current_round}/{num_rounds} \u2014 {game_type.upper()} | Wager: {wager:.4f} MON")

            def on_game_event(evt, _round=current_round):
                """Callback fired from game engine during play - pushes events in real-time."""
                evt["round"] = _round

                # Resolve player names for poker actions
                if evt.get("type") == "poker_action" and "player" in evt:
                    addr = evt["player"]
                    evt["player_name"] = name_a if addr == player_a else name_b

                # Add feed entries for key events
                if evt.get("type") == "rpg_turn":
                    add_feed_event("rpg_turn",
                        f"R{_round} T{evt.get('turn_num', '?')} \u2014 {evt.get('attacker', '?')} uses {evt.get('ability', '?')}")
                elif evt.get("type") == "poker_stage":
                    add_feed_event("poker_round",
                        f"R{_round} \u2014 {evt.get('stage', '?').upper()}")

                match_events.append(evt)

            # RPG: 5 turns per round
            rpg_turns = 5 if game_type == "rpg" else None
            result = mgr.run_match(
                player_a, player_b, gt, wager,
                rpg_max_turns=rpg_turns,
                event_callback=on_game_event,
            )

            winner_name = mgr.agents[result.winner].name
            loser_name = mgr.agents[result.loser].name
            method = result.details.get("win_method", "")

            # Emit round result
            match_events.append({
                "type": "round_result",
                "round": current_round,
                "winner": winner_name,
                "loser": loser_name,
                "winner_addr": result.winner,
                "loser_addr": result.loser,
                "method": method,
                "pot": result.details.get("pot", 0),
            })
            add_feed_event("match_result",
                f"Round {current_round}: {winner_name} beats {loser_name} ({method})")

            if round_idx < num_rounds - 1:
                time.sleep(1.0)  # Pause between rounds

        match_meta["status"] = "complete"
        match_events.append({"type": "complete"})
    except Exception as e:
        logger.error(f"Streaming match error: {e}")
        match_events.append({"type": "error", "message": str(e)})
        match_meta["status"] = "error"
        add_feed_event("error", str(e))
    finally:
        is_running = False


@app.route("/api/demo/run", methods=["POST"])
def api_run_demo():
    """Run the full demo sequence in background."""
    global is_running
    if is_running:
        return jsonify({"error": "Demo already running"}), 409

    is_running = True
    thread = threading.Thread(target=_run_demo_sequence, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Demo started"})


@app.route("/api/tournament/run", methods=["POST"])
def api_run_tournament():
    """Run a single-elimination tournament in background."""
    global is_running
    if is_running:
        return jsonify({"error": "Already running"}), 409

    is_running = True
    thread = threading.Thread(target=_run_tournament_sequence, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Tournament started"})


@app.route("/api/tournament/state")
def api_tournament_state():
    """Get current tournament bracket state."""
    if tournament_state is None:
        return jsonify(None)
    return jsonify(tournament_state)


def _run_demo_sequence():
    """Run a multi-match demo sequence."""
    global is_running
    try:
        mgr = get_arena()

        # Create agents with different personalities
        agents_config = [
            ("Alpha", "aggressive", f"0x{'A1' * 20}"),
            ("Beta", "conservative", f"0x{'B2' * 20}"),
            ("Gamma", "balanced", f"0x{'C3' * 20}"),
            ("Delta", "adaptive", f"0x{'D4' * 20}"),
        ]

        for name, personality, addr in agents_config:
            if addr not in mgr.agents:
                mgr.create_agent(name, addr, personality, 1.0)
                add_feed_event("agent_created", f"{name} ({personality}) joined the arena")
                time.sleep(0.5)

        addresses = [a[2] for a in agents_config]

        # Run 6 poker matches (round-robin)
        matches = [
            (0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2),
        ]

        for i, (a_idx, b_idx) in enumerate(matches):
            add_feed_event("match_start", f"Poker Match {i+1}/6 starting...")
            try:
                result = mgr.run_match(
                    addresses[a_idx], addresses[b_idx],
                    GameType.POKER, 0.05
                )
                winner_name = mgr.agents[result.winner].name
                loser_name = mgr.agents[result.loser].name
                method = result.details.get("win_method", "")
                add_feed_event("match_result", (
                    f"Match {i+1}: {winner_name} beat {loser_name} by {method} | "
                    f"Pot: {result.details.get('pot', 0):.4f} MON"
                ))
                _store_spectator_match(mgr, result, addresses[a_idx], addresses[b_idx])
            except Exception as e:
                add_feed_event("error", f"Match {i+1} failed: {e}")

            time.sleep(1)

        # Run 2 auction matches
        for i in range(2):
            a_idx, b_idx = i, i + 2
            add_feed_event("match_start", f"Auction Match {i+1}/2 starting...")
            try:
                result = mgr.run_match(
                    addresses[a_idx], addresses[b_idx],
                    GameType.AUCTION, 0.05
                )
                winner_name = mgr.agents[result.winner].name
                add_feed_event("match_result", f"Auction {i+1}: {winner_name} wins!")
            except Exception as e:
                add_feed_event("error", f"Auction {i+1} failed: {e}")

            time.sleep(1)

        # Run 2 RPG battles
        rpg_matches = [(0, 3), (1, 2)]
        for i, (a_idx, b_idx) in enumerate(rpg_matches):
            a_name = agents_config[a_idx][0]
            b_name = agents_config[b_idx][0]
            add_feed_event("match_start", f"RPG Battle {i+1}/2: {a_name} vs {b_name}")
            try:
                result = mgr.run_match(
                    addresses[a_idx], addresses[b_idx],
                    GameType.RPG_BATTLE, 0.05
                )
                winner_name = mgr.agents[result.winner].name
                loser_name = mgr.agents[result.loser].name
                method = result.details.get("win_method", "")
                class_a = result.details.get("class_a", "?")
                class_b = result.details.get("class_b", "?")
                add_feed_event("match_result", (
                    f"RPG {i+1}: {winner_name} ({class_a}) defeated "
                    f"{loser_name} ({class_b}) by {method}"
                ))
            except Exception as e:
                add_feed_event("error", f"RPG {i+1} failed: {e}")

            time.sleep(1)

        add_feed_event("demo_complete", "Demo sequence complete! Check the leaderboard.")

    except Exception as e:
        add_feed_event("error", f"Demo error: {e}")
    finally:
        is_running = False


def _store_spectator_match(mgr, result, addr_a, addr_b, trash_talk=None):
    """Store a completed match for spectator mode polling."""
    agent_a = mgr.agents[addr_a]
    agent_b = mgr.agents[addr_b]

    match_data = {
        "game_type": result.game_type.name.lower(),
        "winner": mgr.agents[result.winner].name,
        "loser": mgr.agents[result.loser].name,
        "winner_addr": result.winner,
        "loser_addr": result.loser,
        "player_a_addr": addr_a,
        "player_b_addr": addr_b,
        "player_a_name": agent_a.name,
        "player_b_name": agent_b.name,
        "player_a_personality": agent_a.personality,
        "player_b_personality": agent_b.personality,
        "method": result.details.get("win_method", ""),
        "pot": result.details.get("pot", 0),
        "details": {
            "hand_a": result.details.get("hand_a", ""),
            "hand_b": result.details.get("hand_b", ""),
            "hand_a_name": result.details.get("hand_a_name", ""),
            "hand_b_name": result.details.get("hand_b_name", ""),
            "community": result.details.get("community", ""),
            "rounds": result.details.get("rounds", []),
        },
        "trash_talk": trash_talk,
    }
    completed_matches.append(match_data)


def _generate_trash_talk(mgr, addr_a, addr_b, game_type):
    """Generate trash talk between two agents before a match."""
    agent_a = mgr.agents[addr_a]
    agent_b = mgr.agents[addr_b]

    try:
        talk_a = agent_a.strategy_engine.generate_trash_talk(
            agent_a.name, agent_b.name, agent_b.personality, game_type
        )
    except Exception:
        talk_a = f"Let's go, {agent_b.name}!"

    try:
        talk_b = agent_b.strategy_engine.generate_trash_talk(
            agent_b.name, agent_a.name, agent_a.personality, game_type
        )
    except Exception:
        talk_b = f"Bring it on, {agent_a.name}!"

    return {
        "agent_a_name": agent_a.name,
        "agent_b_name": agent_b.name,
        "agent_a": talk_a,
        "agent_b": talk_b,
        "display": f'{agent_a.name}: "{talk_a}" vs {agent_b.name}: "{talk_b}"',
    }


def _run_tournament_sequence():
    """Run a 4-agent single-elimination tournament with trash talk."""
    global is_running, tournament_state
    try:
        mgr = get_arena()

        # Create agents if needed
        agents_config = [
            ("Alpha", "aggressive", f"0x{'A1' * 20}"),
            ("Beta", "conservative", f"0x{'B2' * 20}"),
            ("Gamma", "balanced", f"0x{'C3' * 20}"),
            ("Delta", "adaptive", f"0x{'D4' * 20}"),
        ]

        for name, personality, addr in agents_config:
            if addr not in mgr.agents:
                mgr.create_agent(name, addr, personality, 1.0)
                add_feed_event("agent_created", f"{name} ({personality}) joined the arena")
                time.sleep(0.3)

        addresses = [a[2] for a in agents_config]
        names = [a[0] for a in agents_config]
        personalities = [a[1] for a in agents_config]

        # Initialize tournament bracket state
        tournament_state = {
            "status": "running",
            "players": [
                {"name": c[0], "personality": c[1], "address": c[2]}
                for c in agents_config
            ],
            "semi_finals": [
                {
                    "player_a": names[0], "player_b": names[1],
                    "pers_a": personalities[0], "pers_b": personalities[1],
                    "winner": None, "status": "pending",
                },
                {
                    "player_a": names[2], "player_b": names[3],
                    "pers_a": personalities[2], "pers_b": personalities[3],
                    "winner": None, "status": "pending",
                },
            ],
            "final": {
                "player_a": None, "player_b": None,
                "pers_a": None, "pers_b": None,
                "winner": None, "status": "pending",
            },
            "champion": None,
            "trash_talks": [],
        }

        add_feed_event("tournament_start",
                        "TOURNAMENT BEGINS! 4 agents, single elimination!")

        # --- Semi-final 1 ---
        tournament_state["semi_finals"][0]["status"] = "playing"
        add_feed_event("match_start", f"Semi-Final 1: {names[0]} vs {names[1]}")

        trash_talk = _generate_trash_talk(mgr, addresses[0], addresses[1], "poker")
        add_feed_event("trash_talk", trash_talk["display"])
        tournament_state["trash_talks"].append(trash_talk)
        time.sleep(2)

        try:
            result1 = mgr.run_match(
                addresses[0], addresses[1], GameType.POKER, 0.1
            )
            w1 = mgr.agents[result1.winner].name
            l1 = mgr.agents[result1.loser].name
            tournament_state["semi_finals"][0]["winner"] = w1
            tournament_state["semi_finals"][0]["status"] = "done"
            add_feed_event("match_result",
                           f"Semi-Final 1: {w1} advances! (beat {l1})")
            _store_spectator_match(
                mgr, result1, addresses[0], addresses[1], trash_talk
            )
        except Exception as e:
            add_feed_event("error", f"Semi-Final 1 failed: {e}")
            tournament_state["semi_finals"][0]["status"] = "error"

        time.sleep(2)

        # --- Semi-final 2 ---
        tournament_state["semi_finals"][1]["status"] = "playing"
        add_feed_event("match_start", f"Semi-Final 2: {names[2]} vs {names[3]}")

        trash_talk = _generate_trash_talk(mgr, addresses[2], addresses[3], "poker")
        add_feed_event("trash_talk", trash_talk["display"])
        tournament_state["trash_talks"].append(trash_talk)
        time.sleep(2)

        try:
            result2 = mgr.run_match(
                addresses[2], addresses[3], GameType.POKER, 0.1
            )
            w2 = mgr.agents[result2.winner].name
            l2 = mgr.agents[result2.loser].name
            tournament_state["semi_finals"][1]["winner"] = w2
            tournament_state["semi_finals"][1]["status"] = "done"
            add_feed_event("match_result",
                           f"Semi-Final 2: {w2} advances! (beat {l2})")
            _store_spectator_match(
                mgr, result2, addresses[2], addresses[3], trash_talk
            )
        except Exception as e:
            add_feed_event("error", f"Semi-Final 2 failed: {e}")
            tournament_state["semi_finals"][1]["status"] = "error"

        time.sleep(2)

        # --- Grand Final ---
        sf1_winner = tournament_state["semi_finals"][0].get("winner")
        sf2_winner = tournament_state["semi_finals"][1].get("winner")

        if sf1_winner and sf2_winner:
            w1_addr = next(
                a[2] for a in agents_config if a[0] == sf1_winner
            )
            w2_addr = next(
                a[2] for a in agents_config if a[0] == sf2_winner
            )
            w1_pers = mgr.agents[w1_addr].personality
            w2_pers = mgr.agents[w2_addr].personality

            tournament_state["final"]["player_a"] = sf1_winner
            tournament_state["final"]["player_b"] = sf2_winner
            tournament_state["final"]["pers_a"] = w1_pers
            tournament_state["final"]["pers_b"] = w2_pers
            tournament_state["final"]["status"] = "playing"

            add_feed_event("match_start",
                           f"GRAND FINAL: {sf1_winner} vs {sf2_winner}!")

            trash_talk = _generate_trash_talk(
                mgr, w1_addr, w2_addr, "poker"
            )
            add_feed_event("trash_talk", trash_talk["display"])
            tournament_state["trash_talks"].append(trash_talk)
            time.sleep(2)

            try:
                result_final = mgr.run_match(
                    w1_addr, w2_addr, GameType.POKER, 0.2
                )
                champion = mgr.agents[result_final.winner].name
                runner_up = mgr.agents[result_final.loser].name
                tournament_state["final"]["winner"] = champion
                tournament_state["final"]["status"] = "done"
                tournament_state["champion"] = champion
                tournament_state["status"] = "complete"
                add_feed_event(
                    "tournament_champion",
                    f"CHAMPION: {champion} wins the tournament! "
                    f"(beat {runner_up} in the final)"
                )
                _store_spectator_match(
                    mgr, result_final, w1_addr, w2_addr, trash_talk
                )
            except Exception as e:
                add_feed_event("error", f"Final failed: {e}")
                tournament_state["final"]["status"] = "error"
        else:
            add_feed_event("error",
                           "Tournament incomplete - semi-finals had errors")
            tournament_state["status"] = "error"

    except Exception as e:
        add_feed_event("error", f"Tournament error: {e}")
        if tournament_state:
            tournament_state["status"] = "error"
    finally:
        is_running = False


def add_feed_event(event_type: str, message: str):
    """Add an event to the live feed."""
    match_feed.append({
        "type": event_type,
        "message": message,
        "timestamp": time.time(),
    })


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    port = int(os.environ.get("PORT", 5000))
    print("\n  MonadArena Web UI starting...")
    print(f"  Open http://localhost:{port} in your browser\n")
    app.run(debug=True, port=port, host="0.0.0.0", use_reloader=False, threaded=True)
