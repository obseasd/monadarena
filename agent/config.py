import os
import sys
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Fix encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


@dataclass
class Config:
    # LLM
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 1024

    # Monad
    rpc_url: str = field(default_factory=lambda: os.getenv("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz"))
    chain_id: int = field(default_factory=lambda: int(os.getenv("MONAD_CHAIN_ID", "10143")))
    private_key: str = field(default_factory=lambda: os.getenv("PRIVATE_KEY", ""))

    # Contracts
    game_arena_address: str = field(default_factory=lambda: os.getenv("GAME_ARENA_ADDRESS", ""))
    tournament_address: str = field(default_factory=lambda: os.getenv("TOURNAMENT_ADDRESS", ""))

    # Agent
    risk_level: str = field(default_factory=lambda: os.getenv("AGENT_RISK_LEVEL", "medium"))
    max_wager_pct: float = field(default_factory=lambda: float(os.getenv("MAX_WAGER_PCT", "0.10")))

    # Network
    is_testnet: bool = True

    @property
    def explorer_url(self) -> str:
        if self.is_testnet:
            return "https://testnet.monadscan.com"
        return "https://monadscan.com"

    def validate(self) -> list[str]:
        errors = []
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY not set")
        if not self.private_key:
            errors.append("PRIVATE_KEY not set")
        if not self.game_arena_address or self.game_arena_address == "0x...":
            errors.append("GAME_ARENA_ADDRESS not set (deploy contracts first)")
        return errors
