"""
RPG Battle engine for MonadArena.
Turn-based 1v1 combat with classes, abilities, HP/MP, and LLM-driven decisions.
"""
import random
import logging
from dataclasses import dataclass, field

from .base import GameBase, GameType, GameResult

logger = logging.getLogger("monadarena.rpg")

# ====== Classes & Abilities ======

CLASSES = {
    "warrior": {
        "name": "Warrior",
        "hp": 120,
        "mp": 40,
        "atk": 18,
        "defense": 14,
        "speed": 8,
        "abilities": {
            "slash": {"damage": 22, "mp_cost": 0, "type": "physical", "desc": "Basic sword slash"},
            "shield_bash": {"damage": 15, "mp_cost": 8, "type": "physical", "desc": "Stun strike, reduces opponent ATK by 3 for 2 turns", "debuff": {"stat": "atk", "amount": -3, "turns": 2}},
            "berserk": {"damage": 35, "mp_cost": 15, "type": "physical", "desc": "Powerful attack but lowers own defense by 4 for 2 turns", "self_debuff": {"stat": "defense", "amount": -4, "turns": 2}},
            "defend": {"damage": 0, "mp_cost": 0, "type": "defend", "desc": "Block stance, halves incoming damage this turn and restores 5 MP", "mp_restore": 5},
            "heal": {"damage": 0, "mp_cost": 12, "type": "heal", "heal_amount": 25, "desc": "Bandage wounds, restore 25 HP"},
        },
    },
    "mage": {
        "name": "Mage",
        "hp": 80,
        "mp": 100,
        "atk": 10,
        "defense": 8,
        "speed": 10,
        "abilities": {
            "fireball": {"damage": 30, "mp_cost": 15, "type": "magic", "desc": "Hurls a fireball dealing 30 magic damage"},
            "ice_shard": {"damage": 18, "mp_cost": 8, "type": "magic", "desc": "Ice projectile, slows opponent (speed -3 for 2 turns)", "debuff": {"stat": "speed", "amount": -3, "turns": 2}},
            "arcane_burst": {"damage": 45, "mp_cost": 30, "type": "magic", "desc": "Devastating arcane explosion, very high damage"},
            "defend": {"damage": 0, "mp_cost": 0, "type": "defend", "desc": "Magical barrier, halves damage this turn and restores 8 MP", "mp_restore": 8},
            "heal": {"damage": 0, "mp_cost": 10, "type": "heal", "heal_amount": 20, "desc": "Healing light, restore 20 HP"},
        },
    },
    "rogue": {
        "name": "Rogue",
        "hp": 90,
        "mp": 60,
        "atk": 16,
        "defense": 10,
        "speed": 16,
        "abilities": {
            "backstab": {"damage": 25, "mp_cost": 5, "type": "physical", "desc": "Quick stab, bonus damage if faster than opponent"},
            "poison_blade": {"damage": 12, "mp_cost": 10, "type": "physical", "desc": "Poison strike, deals 8 damage per turn for 3 turns", "dot": {"damage": 8, "turns": 3}},
            "shadow_strike": {"damage": 38, "mp_cost": 20, "type": "physical", "desc": "Critical strike from the shadows, high damage"},
            "defend": {"damage": 0, "mp_cost": 0, "type": "defend", "desc": "Evasive dodge, halves damage this turn and restores 6 MP", "mp_restore": 6},
            "heal": {"damage": 0, "mp_cost": 10, "type": "heal", "heal_amount": 18, "desc": "Quick bandage, restore 18 HP"},
        },
    },
    "healer": {
        "name": "Healer",
        "hp": 100,
        "mp": 90,
        "atk": 10,
        "defense": 12,
        "speed": 9,
        "abilities": {
            "smite": {"damage": 16, "mp_cost": 5, "type": "magic", "desc": "Holy damage strike"},
            "divine_heal": {"damage": 0, "mp_cost": 15, "type": "heal", "heal_amount": 40, "desc": "Powerful healing, restore 40 HP"},
            "holy_fire": {"damage": 28, "mp_cost": 18, "type": "magic", "desc": "Sacred fire, burns for 6 damage over 2 turns", "dot": {"damage": 6, "turns": 2}},
            "defend": {"damage": 0, "mp_cost": 0, "type": "defend", "desc": "Prayer shield, halves damage and restores 8 MP", "mp_restore": 8},
            "purify": {"damage": 0, "mp_cost": 10, "type": "cleanse", "desc": "Remove all debuffs and DoTs, restore 10 HP", "heal_amount": 10},
        },
    },
}

# Map personality to preferred class
PERSONALITY_CLASS = {
    "aggressive": "warrior",
    "conservative": "healer",
    "balanced": "mage",
    "adaptive": "rogue",
}


@dataclass
class Fighter:
    """A combatant in the RPG battle."""
    address: str
    class_name: str
    name: str  # class display name

    hp: int = 0
    max_hp: int = 0
    mp: int = 0
    max_mp: int = 0
    atk: int = 0
    defense: int = 0
    speed: int = 0

    # Active effects
    buffs: list = field(default_factory=list)   # [{"stat", "amount", "turns"}]
    dots: list = field(default_factory=list)     # [{"damage", "turns"}]
    is_defending: bool = False

    def effective_stat(self, stat: str) -> int:
        """Get stat value including active buffs/debuffs."""
        base = getattr(self, stat)
        modifier = sum(b["amount"] for b in self.buffs if b["stat"] == stat)
        return max(1, base + modifier)

    def tick_effects(self) -> int:
        """Process start-of-turn effects. Returns total DoT damage taken."""
        dot_damage = 0
        for dot in self.dots:
            dot_damage += dot["damage"]
            dot["turns"] -= 1
        self.dots = [d for d in self.dots if d["turns"] > 0]

        for buff in self.buffs:
            buff["turns"] -= 1
        self.buffs = [b for b in self.buffs if b["turns"] > 0]

        self.is_defending = False
        return dot_damage

    def alive(self) -> bool:
        return self.hp > 0

    def status_str(self) -> str:
        effects = []
        if self.dots:
            effects.append(f"DoT:{sum(d['damage'] for d in self.dots)}/turn")
        if self.buffs:
            for b in self.buffs:
                effects.append(f"{b['stat']}{b['amount']:+d}({b['turns']}t)")
        eff = f" [{', '.join(effects)}]" if effects else ""
        return f"{self.name} HP:{self.hp}/{self.max_hp} MP:{self.mp}/{self.max_mp} ATK:{self.effective_stat('atk')} DEF:{self.effective_stat('defense')}{eff}"


def create_fighter(address: str, class_name: str) -> Fighter:
    """Create a Fighter from a class template."""
    cls = CLASSES[class_name]
    return Fighter(
        address=address,
        class_name=class_name,
        name=cls["name"],
        hp=cls["hp"],
        max_hp=cls["hp"],
        mp=cls["mp"],
        max_mp=cls["mp"],
        atk=cls["atk"],
        defense=cls["defense"],
        speed=cls["speed"],
    )


class RPGBattleGame(GameBase):
    """
    Turn-based RPG combat between two AI agents.
    Each agent's personality determines their class.
    LLM decides ability usage each turn.
    """

    MAX_TURNS = 20

    def __init__(self, strategy_engines: dict = None, class_overrides: dict = None, max_turns: int = None, event_callback=None):
        self.strategy_engines = strategy_engines or {}
        self.class_overrides = class_overrides or {}
        if max_turns is not None:
            self.MAX_TURNS = max_turns
        self.event_callback = event_callback
        self.fighters: dict[str, Fighter] = {}
        self.turn_log: list[dict] = []
        self.reasoning_log: list[dict] = []

    def _emit(self, event: dict):
        """Emit a real-time event via callback."""
        if self.event_callback:
            self.event_callback(event)

    def get_game_type(self) -> GameType:
        return GameType.RPG_BATTLE

    def get_state_summary(self) -> str:
        parts = []
        for addr, f in self.fighters.items():
            parts.append(f.status_str())
        return " | ".join(parts) if parts else "No battle in progress"

    def play(self, player_a: str, player_b: str, wager: float) -> GameResult:
        """Play a complete RPG battle."""
        self.turn_log = []
        self.reasoning_log = []

        # Assign classes based on personality or override
        class_a = self._pick_class(player_a)
        class_b = self._pick_class(player_b)

        fighter_a = create_fighter(player_a, class_a)
        fighter_b = create_fighter(player_b, class_b)
        self.fighters = {player_a: fighter_a, player_b: fighter_b}

        logger.info(f"RPG Battle: {fighter_a.name} vs {fighter_b.name}, wager={wager:.4f} MON")

        # Emit init event for real-time streaming
        self._emit({
            "type": "rpg_init",
            "class_a": class_a,
            "class_b": class_b,
            "max_hp_a": fighter_a.max_hp,
            "max_hp_b": fighter_b.max_hp,
            "player_a_addr": player_a,
            "player_b_addr": player_b,
        })

        # Battle loop
        for turn in range(1, self.MAX_TURNS + 1):
            # Determine turn order by speed
            if fighter_a.effective_stat("speed") >= fighter_b.effective_stat("speed"):
                order = [(player_a, fighter_a, fighter_b), (player_b, fighter_b, fighter_a)]
            else:
                order = [(player_b, fighter_b, fighter_a), (player_a, fighter_a, fighter_b)]

            for attacker_addr, attacker, defender in order:
                if not attacker.alive() or not defender.alive():
                    break

                # Tick DoTs and buffs at start of each fighter's action
                dot_dmg = attacker.tick_effects()
                if dot_dmg > 0:
                    attacker.hp = max(0, attacker.hp - dot_dmg)
                    logger.info(f"  Turn {turn}: {attacker.name} takes {dot_dmg} DoT damage (HP: {attacker.hp})")
                    if not attacker.alive():
                        break

                # Get LLM decision
                decision = self._get_decision(attacker_addr, attacker, defender, turn)
                ability_name = decision.get("ability", "slash")

                # Resolve ability
                self._resolve_ability(attacker, defender, ability_name, turn)

                # Emit turn event for real-time streaming
                if self.turn_log:
                    log_entry = self.turn_log[-1]
                    self._emit({
                        "type": "rpg_turn",
                        "turn_num": turn,
                        "attacker_addr": attacker_addr,
                        **log_entry,
                        "hp_a": fighter_a.hp,
                        "hp_b": fighter_b.hp,
                        "mp_a": fighter_a.mp,
                        "mp_b": fighter_b.mp,
                    })

                if not defender.alive():
                    break

            # Check for battle end
            if not fighter_a.alive() or not fighter_b.alive():
                break

        # Determine winner
        if fighter_a.alive() and not fighter_b.alive():
            winner, loser = player_a, player_b
        elif fighter_b.alive() and not fighter_a.alive():
            winner, loser = player_b, player_a
        elif fighter_a.hp > fighter_b.hp:
            winner, loser = player_a, player_b
        elif fighter_b.hp > fighter_a.hp:
            winner, loser = player_b, player_a
        else:
            # True tie - first player wins by default
            winner, loser = player_a, player_b

        win_method = "KO" if (not self.fighters[loser].alive()) else "HP advantage"

        logger.info(f"  WINNER: {self.fighters[winner].name} by {win_method}")
        logger.info(f"  Final: {fighter_a.status_str()} | {fighter_b.status_str()}")

        self._emit({
            "type": "rpg_end",
            "final_hp_a": fighter_a.hp,
            "final_hp_b": fighter_b.hp,
        })

        return GameResult(
            game_type=GameType.RPG_BATTLE,
            winner=winner,
            loser=loser,
            wager=wager,
            details={
                "class_a": class_a,
                "class_b": class_b,
                "final_hp_a": fighter_a.hp,
                "final_hp_b": fighter_b.hp,
                "max_hp_a": fighter_a.max_hp,
                "max_hp_b": fighter_b.max_hp,
                "turns": len(self.turn_log),
                "win_method": win_method,
                "turn_log": self.turn_log,
            },
            rounds_played=len(self.turn_log),
            reasoning_log=self.reasoning_log,
        )

    def _pick_class(self, address: str) -> str:
        """Pick class based on override, engine personality, or random."""
        if address in self.class_overrides:
            return self.class_overrides[address]

        engine = self.strategy_engines.get(address)
        if engine and hasattr(engine, "personality"):
            return PERSONALITY_CLASS.get(engine.personality, "mage")

        return random.choice(list(CLASSES.keys()))

    def _get_decision(self, address: str, attacker: Fighter, defender: Fighter, turn: int) -> dict:
        """Get ability choice from strategy engine."""
        engine = self.strategy_engines.get(address)

        # Build available abilities
        cls = CLASSES[attacker.class_name]
        available = {}
        for name, info in cls["abilities"].items():
            if attacker.mp >= info["mp_cost"]:
                available[name] = info

        if not available:
            # Only defend if no MP for anything
            available = {"defend": cls["abilities"]["defend"]}

        if engine is None:
            # Random fallback
            choice = random.choice(list(available.keys()))
            decision = {"ability": choice, "reasoning": "random choice"}
        else:
            decision = engine.decide_rpg_action(
                your_fighter=attacker.status_str(),
                opponent_fighter=defender.status_str(),
                available_abilities={k: v["desc"] + f" (MP cost: {v['mp_cost']}, DMG: {v.get('damage', 0)})" for k, v in available.items()},
                turn=turn,
                max_turns=self.MAX_TURNS,
            )

        # Validate choice
        ability = decision.get("ability", "")
        if ability not in available:
            ability = list(available.keys())[0]
            decision["ability"] = ability

        self.reasoning_log.append({
            "player": address,
            "turn": turn,
            "fighter": attacker.status_str(),
            "opponent": defender.status_str(),
            "decision": decision,
        })

        return decision

    def _resolve_ability(self, attacker: Fighter, defender: Fighter, ability_name: str, turn: int):
        """Resolve an ability's effects."""
        cls = CLASSES[attacker.class_name]
        ability = cls["abilities"].get(ability_name)
        if not ability:
            return

        # Spend MP
        attacker.mp = max(0, attacker.mp - ability["mp_cost"])

        log_entry = {
            "turn": turn,
            "attacker": attacker.name,
            "ability": ability_name,
            "type": ability["type"],
        }

        if ability["type"] == "defend":
            attacker.is_defending = True
            mp_restore = ability.get("mp_restore", 0)
            attacker.mp = min(attacker.max_mp, attacker.mp + mp_restore)
            log_entry["effect"] = f"defending (+{mp_restore} MP)"
            logger.info(f"  Turn {turn}: {attacker.name} DEFENDS (+{mp_restore} MP)")

        elif ability["type"] == "heal":
            heal = ability.get("heal_amount", 0)
            attacker.hp = min(attacker.max_hp, attacker.hp + heal)
            log_entry["effect"] = f"healed {heal} HP"
            logger.info(f"  Turn {turn}: {attacker.name} HEALS +{heal} HP (now {attacker.hp})")

        elif ability["type"] == "cleanse":
            attacker.dots = []
            attacker.buffs = [b for b in attacker.buffs if b["amount"] > 0]  # Keep positive buffs
            heal = ability.get("heal_amount", 0)
            attacker.hp = min(attacker.max_hp, attacker.hp + heal)
            log_entry["effect"] = f"cleansed all debuffs, healed {heal}"
            logger.info(f"  Turn {turn}: {attacker.name} PURIFIES (cleanse + {heal} HP)")

        elif ability["type"] in ("physical", "magic"):
            # Calculate damage
            base_damage = ability["damage"]

            if ability["type"] == "physical":
                # Physical: scale with ATK vs DEF
                atk_mod = attacker.effective_stat("atk") / 15.0
                def_mod = defender.effective_stat("defense") / 20.0
                damage = max(1, int(base_damage * atk_mod - base_damage * def_mod * 0.3))
            else:
                # Magic: less affected by defense
                damage = max(1, int(base_damage * 0.9 + attacker.effective_stat("atk") * 0.2 - defender.effective_stat("defense") * 0.15))

            # Backstab bonus (rogue)
            if ability_name == "backstab" and attacker.effective_stat("speed") > defender.effective_stat("speed"):
                damage = int(damage * 1.4)

            # Defending halves damage
            if defender.is_defending:
                damage = max(1, damage // 2)

            # Apply damage
            defender.hp = max(0, defender.hp - damage)

            log_entry["damage"] = damage
            log_entry["defender_hp"] = defender.hp
            logger.info(f"  Turn {turn}: {attacker.name} uses {ability_name} -> {damage} dmg (opponent HP: {defender.hp})")

            # Apply debuff to opponent
            if "debuff" in ability:
                d = ability["debuff"]
                defender.buffs.append({"stat": d["stat"], "amount": d["amount"], "turns": d["turns"]})
                log_entry["debuff"] = f"{d['stat']} {d['amount']:+d} for {d['turns']}t"

            # Apply self-debuff
            if "self_debuff" in ability:
                d = ability["self_debuff"]
                attacker.buffs.append({"stat": d["stat"], "amount": d["amount"], "turns": d["turns"]})
                log_entry["self_debuff"] = f"{d['stat']} {d['amount']:+d} for {d['turns']}t"

            # Apply DoT
            if "dot" in ability:
                d = ability["dot"]
                defender.dots.append({"damage": d["damage"], "turns": d["turns"]})
                log_entry["dot"] = f"{d['damage']} dmg/turn for {d['turns']}t"

        self.turn_log.append(log_entry)
