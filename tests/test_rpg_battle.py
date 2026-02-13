"""Tests for the RPG battle game engine."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.rpg_battle import (
    RPGBattleGame, Fighter, create_fighter,
    CLASSES, PERSONALITY_CLASS,
)
from games.base import GameType, GameResult


class TestClasses:
    def test_all_classes_exist(self):
        assert "warrior" in CLASSES
        assert "mage" in CLASSES
        assert "rogue" in CLASSES
        assert "healer" in CLASSES

    def test_class_has_required_fields(self):
        for name, cls in CLASSES.items():
            assert "hp" in cls
            assert "mp" in cls
            assert "atk" in cls
            assert "defense" in cls
            assert "speed" in cls
            assert "abilities" in cls
            assert len(cls["abilities"]) >= 4, f"{name} should have at least 4 abilities"

    def test_all_classes_have_defend(self):
        for name, cls in CLASSES.items():
            assert "defend" in cls["abilities"], f"{name} missing defend ability"

    def test_personality_class_mapping(self):
        assert PERSONALITY_CLASS["aggressive"] == "warrior"
        assert PERSONALITY_CLASS["conservative"] == "healer"
        assert PERSONALITY_CLASS["balanced"] == "mage"
        assert PERSONALITY_CLASS["adaptive"] == "rogue"


class TestFighter:
    def test_create_warrior(self):
        f = create_fighter("0x111", "warrior")
        assert f.hp == 120
        assert f.max_hp == 120
        assert f.mp == 40
        assert f.atk == 18
        assert f.alive()

    def test_create_mage(self):
        f = create_fighter("0x222", "mage")
        assert f.hp == 80
        assert f.mp == 100
        assert f.name == "Mage"

    def test_effective_stat_with_debuff(self):
        f = create_fighter("0x111", "warrior")
        f.buffs.append({"stat": "atk", "amount": -5, "turns": 2})
        assert f.effective_stat("atk") == 13  # 18 - 5

    def test_effective_stat_minimum_1(self):
        f = create_fighter("0x111", "warrior")
        f.buffs.append({"stat": "atk", "amount": -100, "turns": 2})
        assert f.effective_stat("atk") == 1  # min 1

    def test_tick_effects_dots(self):
        f = create_fighter("0x111", "warrior")
        f.dots.append({"damage": 10, "turns": 2})
        dmg = f.tick_effects()
        assert dmg == 10
        assert len(f.dots) == 1  # 1 turn remaining
        dmg2 = f.tick_effects()
        assert dmg2 == 10
        assert len(f.dots) == 0  # expired

    def test_tick_effects_buffs_expire(self):
        f = create_fighter("0x111", "warrior")
        f.buffs.append({"stat": "atk", "amount": -3, "turns": 1})
        f.tick_effects()
        assert len(f.buffs) == 0  # expired

    def test_tick_resets_defending(self):
        f = create_fighter("0x111", "warrior")
        f.is_defending = True
        f.tick_effects()
        assert f.is_defending is False

    def test_status_str(self):
        f = create_fighter("0x111", "warrior")
        s = f.status_str()
        assert "Warrior" in s
        assert "HP:120" in s
        assert "MP:40" in s

    def test_alive_check(self):
        f = create_fighter("0x111", "warrior")
        assert f.alive() is True
        f.hp = 0
        assert f.alive() is False


class TestRPGBattleGame:
    def test_game_type(self):
        game = RPGBattleGame()
        assert game.get_game_type() == GameType.RPG_BATTLE

    def test_play_returns_result(self):
        """Battle with random fallback (no strategy engines)."""
        game = RPGBattleGame()
        result = game.play("0xAAA", "0xBBB", 0.05)

        assert isinstance(result, GameResult)
        assert result.game_type == GameType.RPG_BATTLE
        assert result.winner in ["0xAAA", "0xBBB"]
        assert result.loser in ["0xAAA", "0xBBB"]
        assert result.winner != result.loser
        assert result.wager == 0.05

    def test_result_has_details(self):
        game = RPGBattleGame()
        result = game.play("0xAAA", "0xBBB", 0.05)

        assert "class_a" in result.details
        assert "class_b" in result.details
        assert "final_hp_a" in result.details
        assert "final_hp_b" in result.details
        assert "win_method" in result.details
        assert "turns" in result.details
        assert result.details["win_method"] in ("KO", "HP advantage")

    def test_class_override(self):
        game = RPGBattleGame(class_overrides={
            "0xAAA": "warrior",
            "0xBBB": "mage",
        })
        result = game.play("0xAAA", "0xBBB", 0.05)
        assert result.details["class_a"] == "warrior"
        assert result.details["class_b"] == "mage"

    def test_max_turns_limit(self):
        """Game shouldn't exceed MAX_TURNS."""
        game = RPGBattleGame()
        game.MAX_TURNS = 5
        result = game.play("0xAAA", "0xBBB", 0.05)
        assert result.details["turns"] <= 10  # 2 actions per turn max

    def test_battle_has_turn_log(self):
        game = RPGBattleGame()
        result = game.play("0xAAA", "0xBBB", 0.05)
        assert len(result.details["turn_log"]) > 0

    def test_state_summary(self):
        game = RPGBattleGame()
        assert game.get_state_summary() == "No battle in progress"

        # After a fight starts, fighters dict is populated
        game.play("0xAAA", "0xBBB", 0.05)
        summary = game.get_state_summary()
        assert "HP:" in summary


class TestResolveAbility:
    def test_defend_restores_mp(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "warrior")
        f.mp = 10
        d = create_fighter("0x222", "mage")
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "defend", 1)
        assert f.is_defending is True
        assert f.mp == 15  # 10 + 5 (warrior defend)

    def test_heal_restores_hp(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "warrior")
        f.hp = 50
        d = create_fighter("0x222", "mage")
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "heal", 1)
        assert f.hp == 75  # 50 + 25 (warrior heal)

    def test_heal_does_not_exceed_max(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "warrior")
        f.hp = 110  # close to max 120
        d = create_fighter("0x222", "mage")
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "heal", 1)
        assert f.hp == 120  # capped at max

    def test_attack_deals_damage(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "warrior")
        d = create_fighter("0x222", "mage")
        initial_hp = d.hp
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "slash", 1)
        assert d.hp < initial_hp

    def test_defending_halves_damage(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "warrior")
        d1 = create_fighter("0x222", "mage")
        d2 = create_fighter("0x333", "mage")
        d2.is_defending = True
        game.fighters = {"0x111": f, "0x222": d1, "0x333": d2}

        game._resolve_ability(f, d1, "slash", 1)
        dmg_normal = 80 - d1.hp  # mage has 80 HP

        d1_hp_after = d1.hp
        game._resolve_ability(f, d2, "slash", 1)
        dmg_defending = 80 - d2.hp

        assert dmg_defending < dmg_normal

    def test_debuff_applied(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "warrior")
        d = create_fighter("0x222", "mage")
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "shield_bash", 1)
        assert len(d.buffs) == 1
        assert d.buffs[0]["stat"] == "atk"
        assert d.buffs[0]["amount"] == -3

    def test_dot_applied(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "rogue")
        d = create_fighter("0x222", "warrior")
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "poison_blade", 1)
        assert len(d.dots) == 1
        assert d.dots[0]["damage"] == 8
        assert d.dots[0]["turns"] == 3

    def test_mp_consumed(self):
        game = RPGBattleGame()
        f = create_fighter("0x111", "mage")
        d = create_fighter("0x222", "warrior")
        initial_mp = f.mp
        game.fighters = {"0x111": f, "0x222": d}

        game._resolve_ability(f, d, "fireball", 1)
        assert f.mp == initial_mp - 15  # fireball costs 15 MP
