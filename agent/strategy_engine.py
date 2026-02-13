"""
LLM-powered strategy engine for MonadArena.
All strategic decisions go through the LLM - no heuristic shortcuts.
Each agent has a distinct personality that shapes its LLM prompts.
"""
import json
import logging
from anthropic import Anthropic

from .config import Config
from .opponent_model import OpponentModel
from .bankroll import BankrollManager

logger = logging.getLogger("monadarena.strategy")


# Personality-specific system prompts - these create genuinely different agents
PERSONALITY_PROMPTS = {
    "aggressive": (
        "You are an AGGRESSIVE poker player. You prefer to bet and raise rather than call or fold. "
        "You apply maximum pressure with frequent raises, large bet sizes, and well-timed bluffs. "
        "You rarely fold unless your hand is truly hopeless AND you face a big raise. "
        "You see weakness in opponents and exploit it with big bets. "
        "When in doubt, RAISE. Your bluff frequency is high (30-40%). "
        "Minimum raise size should be 50-75% of the pot."
    ),
    "conservative": (
        "You are a CONSERVATIVE poker player. You only play strong hands and fold marginal ones. "
        "You prefer calling over raising and only raise with premium holdings (top pair+, overpairs). "
        "You rarely bluff (under 10%) and wait patiently for the best spots. "
        "You protect your bankroll above all else. When in doubt, CALL rather than fold, "
        "but FOLD if you have bottom pair or worse facing a raise."
    ),
    "balanced": (
        "You are a BALANCED poker player who mixes aggression with discipline. "
        "You raise with strong hands, call with decent draws and pairs, fold true garbage. "
        "You bluff occasionally (15-25%) to stay unpredictable - especially on scary boards. "
        "You size your bets based on pot odds: 50-70% pot for value, 30-50% for bluffs. "
        "You adapt based on position, pot odds, and opponent tendencies."
    ),
    "adaptive": (
        "You are an ADAPTIVE poker player. Your primary strength is reading opponents. "
        "Against aggressive opponents: trap with strong hands (just call), then raise river. "
        "Against passive opponents: bluff more, bet big with draws, steal pots aggressively. "
        "Against tight opponents: raise their blinds, pressure their folds. "
        "Against loose opponents: tighten up, value bet relentlessly. "
        "USE THE OPPONENT DATA to make every decision. Adjust your bluff frequency based on their fold rate."
    ),
}

PERSONALITY_AUCTION = {
    "aggressive": "You bid aggressively, 10-20% above estimated value to ensure wins. You hate losing auctions.",
    "conservative": "You bid conservatively, always 15-25% below estimated value. Missing items is fine; overpaying is not.",
    "balanced": "You bid at fair value with slight adjustments based on competition. Target 5-10% below value.",
    "adaptive": "You study opponent bid history carefully and bid just enough to win. Outbid predictable opponents by the minimum margin.",
}


POKER_SYSTEM_TEMPLATE = """You are an expert AI poker player competing in heads-up Texas Hold'em on the Monad blockchain.

YOUR PERSONALITY: {personality_desc}

CRITICAL RULES:
- Stay FULLY in character with your personality for EVERY decision
- Do NOT fold preflop with any Ace, any King, any pocket pair, or suited connectors
- With top pair or better, you MUST raise (not just call)
- Consider bluffing with draws (flush draws, straight draws) - that's smart poker
- When to_call is 0.0, you can CHECK (action: "call") or BET (action: "raise") - never fold for free
- raise_amount should be meaningful: at least 25% of the pot, up to 100% of the pot
- Always respond with valid JSON only - no markdown, no extra text."""

POKER_DECISION_TEMPLATE = """GAME STATE:
- Your hand: {hole_cards}
- Community cards: {community_cards}
- Pot size: {pot} MON
- Your stack: {stack} MON
- Opponent stack: {opp_stack} MON
- Position: {position}
- Current bet to call: {to_call} MON
- Round: {round}

{opponent_context}

{bankroll_context}

Analyze step by step:
1. Hand strength: What do you have? Estimate win probability (be specific with %)
2. Pot odds: Is calling profitable? (to_call / (pot + to_call))
3. Opponent read: Based on their profile, what are they likely holding?
4. Your personality says to play {personality_style} - what does that mean here?
5. Bluff assessment: Would a bluff work here given the board and opponent?

Respond in this EXACT JSON format:
{{
    "reasoning": "Your step-by-step analysis (2-4 sentences, be specific)",
    "action": "fold" or "call" or "raise",
    "raise_amount": 0.0,
    "confidence": 0.0,
    "bluff_probability": 0.0,
    "estimated_win_prob": 0.0
}}"""


AUCTION_SYSTEM_TEMPLATE = """You are a strategic bidder in blind auctions on the Monad blockchain.

YOUR PERSONALITY: {personality_desc}

RULES:
- Always bid a positive amount (at least 0.001 MON) - passing wastes opportunities
- Stay in character with your personality
- Always respond with valid JSON only - no markdown, no extra text."""

AUCTION_DECISION_TEMPLATE = """AUCTION STATE:
- Item: {item_description}
- Estimated value: {estimated_value} MON (range: {min_value}-{max_value})
- Your budget: {budget} MON
- Number of bidders: {num_bidders}
- Round: {round}/{total_rounds}

{opponent_context}

{bankroll_context}

PREVIOUS BIDS THIS AUCTION:
{bid_history}

Analyze:
1. What is the item truly worth to you?
2. What will competitors likely bid based on their history?
3. What's the optimal bid to maximize your expected profit?
4. Budget management - how much can you afford?

Respond in this exact JSON format:
{{
    "reasoning": "Your analysis (2-4 sentences)",
    "bid_amount": 0.0,
    "confidence": 0.0,
    "strategy": "aggressive" or "conservative" or "value"
}}"""


PERSONALITY_RPG = {
    "aggressive": "You are a BERSERKER. Always pick the highest-damage ability. Attack relentlessly. Only heal when below 20% HP. Never defend - it wastes turns.",
    "conservative": "You are a GUARDIAN. Prioritize survival: heal often, defend when low, use DoTs for safe damage. Conserve MP for heals. Patience wins.",
    "balanced": "You are a TACTICIAN. Analyze HP/MP ratios. Use high-damage abilities when the opponent is vulnerable. Defend when expecting a big hit. Heal proactively around 50% HP.",
    "adaptive": "You are a STRATEGIST. Read the opponent's pattern. If they attack a lot, defend then counter. If they heal, use your strongest attack. Mirror their weakness.",
}


RPG_SYSTEM_TEMPLATE = """You are an expert AI RPG fighter in a turn-based combat arena on the Monad blockchain.

YOUR PERSONALITY: {personality_desc}

RULES:
- Pick ONE ability from the available options each turn
- Manage your MP carefully - if you run out, you can only defend
- Defending halves damage AND restores MP - use it tactically
- DoT effects stack and tick every turn - they're efficient damage
- HP management is key: don't waste heals when at high HP
- Speed determines who acts first each turn
- Always respond with valid JSON only - no markdown, no extra text."""


RPG_DECISION_TEMPLATE = """BATTLE STATE:
- Your fighter: {your_fighter}
- Opponent: {opponent_fighter}
- Turn: {turn}/{max_turns}

AVAILABLE ABILITIES:
{abilities_list}

Analyze:
1. HP comparison: Who is winning? How many hits can each take?
2. MP management: Can you afford your best moves? Should you defend to regen MP?
3. Status effects: Any DoTs or debuffs to account for?
4. Opponent prediction: What will they likely do this turn?
5. Win condition: What's your path to victory from here?

Respond in this EXACT JSON format:
{{
    "reasoning": "Your tactical analysis (2-3 sentences)",
    "ability": "ability_name_here",
    "confidence": 0.0
}}"""


class StrategyEngine:
    """LLM-powered strategy engine with personality-driven decisions."""

    def __init__(self, config: Config, personality: str = "balanced"):
        self.config = config
        self.personality = personality
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.decision_log: list[dict] = []

    def _get_poker_system_prompt(self) -> str:
        desc = PERSONALITY_PROMPTS.get(self.personality, PERSONALITY_PROMPTS["balanced"])
        return POKER_SYSTEM_TEMPLATE.format(personality_desc=desc)

    def _get_auction_system_prompt(self) -> str:
        desc = PERSONALITY_AUCTION.get(self.personality, PERSONALITY_AUCTION["balanced"])
        return AUCTION_SYSTEM_TEMPLATE.format(personality_desc=desc)

    def _get_rpg_system_prompt(self) -> str:
        desc = PERSONALITY_RPG.get(self.personality, PERSONALITY_RPG["balanced"])
        return RPG_SYSTEM_TEMPLATE.format(personality_desc=desc)

    def _call_llm(self, system: str, prompt: str) -> str:
        """Make an LLM API call and return the response text."""
        try:
            response = self.client.messages.create(
                model=self.config.llm_model,
                max_tokens=self.config.llm_max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from LLM response, handling common issues."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        return json.loads(cleaned)

    def decide_poker_action(
        self,
        hole_cards: list[str],
        community_cards: list[str],
        pot: float,
        stack: float,
        opp_stack: float,
        position: str,
        to_call: float,
        round_name: str,
        opponent: OpponentModel | None = None,
        bankroll: BankrollManager | None = None,
    ) -> dict:
        """
        Make a poker decision using the LLM with personality.

        Returns dict with: reasoning, action, raise_amount, confidence, bluff_probability, estimated_win_prob
        """
        opponent_ctx = opponent.to_prompt_context() if opponent else "No opponent data yet - play your default style."
        bankroll_ctx = bankroll.to_prompt_context() if bankroll else "No bankroll data."

        prompt = POKER_DECISION_TEMPLATE.format(
            hole_cards=", ".join(hole_cards),
            community_cards=", ".join(community_cards) if community_cards else "None (preflop)",
            pot=f"{pot:.4f}",
            stack=f"{stack:.4f}",
            opp_stack=f"{opp_stack:.4f}",
            position=position,
            to_call=f"{to_call:.4f}",
            round=round_name,
            opponent_context=opponent_ctx,
            bankroll_context=bankroll_ctx,
            personality_style=self.personality,
        )

        raw = self._call_llm(self._get_poker_system_prompt(), prompt)
        decision = self._parse_json(raw)

        # Validate and sanitize
        decision.setdefault("action", "fold")
        decision.setdefault("raise_amount", 0.0)
        decision.setdefault("confidence", 0.5)
        decision.setdefault("bluff_probability", 0.0)
        decision.setdefault("estimated_win_prob", 0.5)

        if decision["action"] not in ("fold", "call", "raise"):
            decision["action"] = "fold"

        # Don't fold when there's nothing to call (check instead)
        if decision["action"] == "fold" and to_call <= 0:
            decision["action"] = "call"  # Check

        # Log the decision
        log_entry = {
            "game_type": "poker",
            "personality": self.personality,
            "round": round_name,
            "hole_cards": hole_cards,
            "community_cards": community_cards,
            "decision": decision,
        }
        self.decision_log.append(log_entry)
        logger.info(
            f"[{self.personality}] Poker: {decision['action']} "
            f"(conf={decision['confidence']:.0%}, bluff={decision['bluff_probability']:.0%})"
        )

        return decision

    def decide_auction_bid(
        self,
        item_description: str,
        estimated_value: float,
        min_value: float,
        max_value: float,
        budget: float,
        num_bidders: int,
        round_num: int,
        total_rounds: int,
        bid_history: list[dict] | None = None,
        opponent: OpponentModel | None = None,
        bankroll: BankrollManager | None = None,
    ) -> dict:
        """
        Make an auction bidding decision using the LLM with personality.

        Returns dict with: reasoning, bid_amount, confidence, strategy
        """
        opponent_ctx = opponent.to_prompt_context() if opponent else "No opponent data yet."
        bankroll_ctx = bankroll.to_prompt_context() if bankroll else "No bankroll data."

        history_str = "None yet."
        if bid_history:
            history_str = "\n".join(
                f"  Round {b['round']}: You bid {b.get('your_bid', '?')}, "
                f"Winner bid {b.get('winning_bid', '?')}"
                for b in bid_history
            )

        prompt = AUCTION_DECISION_TEMPLATE.format(
            item_description=item_description,
            estimated_value=f"{estimated_value:.4f}",
            min_value=f"{min_value:.4f}",
            max_value=f"{max_value:.4f}",
            budget=f"{budget:.4f}",
            num_bidders=num_bidders,
            round=round_num,
            total_rounds=total_rounds,
            bid_history=history_str,
            opponent_context=opponent_ctx,
            bankroll_context=bankroll_ctx,
        )

        raw = self._call_llm(self._get_auction_system_prompt(), prompt)
        decision = self._parse_json(raw)

        # Validate
        decision.setdefault("bid_amount", 0.0)
        decision.setdefault("confidence", 0.5)
        decision.setdefault("strategy", "value")

        # Clamp bid to budget, ensure minimum positive bid
        decision["bid_amount"] = min(decision["bid_amount"], budget)
        decision["bid_amount"] = max(decision["bid_amount"], 0.001)

        log_entry = {
            "game_type": "auction",
            "personality": self.personality,
            "round": round_num,
            "item": item_description,
            "decision": decision,
        }
        self.decision_log.append(log_entry)
        logger.info(
            f"[{self.personality}] Auction bid: {decision['bid_amount']:.4f} MON ({decision['strategy']})"
        )

        return decision

    def decide_rpg_action(
        self,
        your_fighter: str,
        opponent_fighter: str,
        available_abilities: dict[str, str],
        turn: int,
        max_turns: int,
    ) -> dict:
        """
        Make an RPG combat decision using the LLM.

        Returns dict with: reasoning, ability, confidence
        """
        abilities_str = "\n".join(
            f"  - {name}: {desc}" for name, desc in available_abilities.items()
        )

        prompt = RPG_DECISION_TEMPLATE.format(
            your_fighter=your_fighter,
            opponent_fighter=opponent_fighter,
            turn=turn,
            max_turns=max_turns,
            abilities_list=abilities_str,
        )

        raw = self._call_llm(self._get_rpg_system_prompt(), prompt)
        decision = self._parse_json(raw)

        decision.setdefault("ability", list(available_abilities.keys())[0])
        decision.setdefault("confidence", 0.5)

        # Validate ability choice
        if decision["ability"] not in available_abilities:
            decision["ability"] = list(available_abilities.keys())[0]

        log_entry = {
            "game_type": "rpg_battle",
            "personality": self.personality,
            "turn": turn,
            "decision": decision,
        }
        self.decision_log.append(log_entry)
        logger.info(
            f"[{self.personality}] RPG: {decision['ability']} (conf={decision.get('confidence', 0):.0%})"
        )

        return decision

    def decide_wager_amount(
        self,
        game_type: str,
        opponent: OpponentModel | None,
        bankroll: BankrollManager,
    ) -> dict:
        """Decide how much to wager on a new game."""
        prompt = f"""You are deciding how much MON to wager on a {game_type} game.

{bankroll.to_prompt_context()}

{opponent.to_prompt_context() if opponent else "Unknown opponent."}

Consider:
1. Your bankroll and risk tolerance
2. Your edge against this opponent (if known)
3. Kelly Criterion for optimal sizing

Respond in JSON:
{{
    "reasoning": "Your analysis",
    "wager_amount": 0.0,
    "confidence": 0.0
}}"""

        raw = self._call_llm(self._get_poker_system_prompt(), prompt)
        decision = self._parse_json(raw)

        # Clamp to valid range
        max_w = bankroll.max_wager()
        decision["wager_amount"] = min(decision.get("wager_amount", 0.001), max_w)
        decision["wager_amount"] = max(decision["wager_amount"], 0.001)

        return decision

    def generate_trash_talk(
        self,
        my_name: str,
        opponent_name: str,
        opponent_personality: str,
        game_type: str,
    ) -> str:
        """Generate pre-match trash talk using the LLM."""
        system = (
            f"You are {my_name}, a {self.personality} competitor in a blockchain gaming arena. "
            f"Generate a single SHORT trash talk line (max 20 words) before facing {opponent_name} "
            f"(who plays {opponent_personality} style) in {game_type}. "
            f"Be witty, creative, and stay in-character with your {self.personality} personality. "
            f"Output ONLY the trash talk line, nothing else. No quotes."
        )
        prompt = f"Trash talk {opponent_name} before your {game_type} match. One line only."
        try:
            return self._call_llm(system, prompt).strip().strip('"\'')
        except Exception:
            return f"Let's see what you've got, {opponent_name}."

    def get_decision_log(self) -> list[dict]:
        """Return the full decision log for review."""
        return self.decision_log.copy()
