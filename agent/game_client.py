"""
Smart contract interaction layer for MonadArena.
Handles all on-chain operations: create/join games, commit/reveal, claim payouts.
"""
import json
import os
import logging
from web3 import Web3
from eth_account import Account

from .config import Config

logger = logging.getLogger("monadarena.client")

# ABI definitions (key functions only)
GAME_ARENA_ABI = json.loads("""[
    {
        "inputs": [{"internalType": "uint8", "name": "_gameType", "type": "uint8"}],
        "name": "createGame",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_gameId", "type": "uint256"}],
        "name": "joinGame",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_gameId", "type": "uint256"},
            {"internalType": "bytes32", "name": "_commitment", "type": "bytes32"}
        ],
        "name": "commitMove",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_gameId", "type": "uint256"},
            {"internalType": "bytes", "name": "_move", "type": "bytes"},
            {"internalType": "bytes32", "name": "_salt", "type": "bytes32"}
        ],
        "name": "revealMove",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_gameId", "type": "uint256"},
            {"internalType": "address", "name": "_winner", "type": "address"}
        ],
        "name": "resolveGameByOracle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_gameId", "type": "uint256"}],
        "name": "cancelGame",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_gameId", "type": "uint256"}],
        "name": "getGame",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "id", "type": "uint256"},
                    {"internalType": "uint8", "name": "gameType", "type": "uint8"},
                    {"internalType": "address", "name": "playerA", "type": "address"},
                    {"internalType": "address", "name": "playerB", "type": "address"},
                    {"internalType": "uint256", "name": "wager", "type": "uint256"},
                    {"internalType": "uint8", "name": "state", "type": "uint8"},
                    {"internalType": "address", "name": "winner", "type": "address"},
                    {"internalType": "uint256", "name": "createdAt", "type": "uint256"},
                    {"internalType": "uint256", "name": "resolvedAt", "type": "uint256"},
                    {"internalType": "bytes32", "name": "commitA", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "commitB", "type": "bytes32"},
                    {"internalType": "bytes", "name": "revealA", "type": "bytes"},
                    {"internalType": "bytes", "name": "revealB", "type": "bytes"}
                ],
                "internalType": "struct GameArena.Game",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "_player", "type": "address"}],
        "name": "getPlayerStats",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "gamesPlayed", "type": "uint256"},
                    {"internalType": "uint256", "name": "wins", "type": "uint256"},
                    {"internalType": "uint256", "name": "losses", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalWagered", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalWon", "type": "uint256"}
                ],
                "internalType": "struct GameArena.PlayerStats",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "gameCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getContractBalance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "name": "gameId", "type": "uint256"},
            {"indexed": true, "name": "playerA", "type": "address"},
            {"indexed": false, "name": "gameType", "type": "uint8"},
            {"indexed": false, "name": "wager", "type": "uint256"}
        ],
        "name": "GameCreated",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "name": "gameId", "type": "uint256"},
            {"indexed": true, "name": "winner", "type": "address"},
            {"indexed": false, "name": "payout", "type": "uint256"}
        ],
        "name": "GameResolved",
        "type": "event"
    }
]""")

TOURNAMENT_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "string", "name": "_name", "type": "string"},
            {"internalType": "uint8", "name": "_gameType", "type": "uint8"},
            {"internalType": "uint256", "name": "_entryFee", "type": "uint256"},
            {"internalType": "uint256", "name": "_maxPlayers", "type": "uint256"}
        ],
        "name": "createTournament",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_tournamentId", "type": "uint256"}],
        "name": "register",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_tournamentId", "type": "uint256"},
            {"internalType": "uint256", "name": "_matchIndex", "type": "uint256"},
            {"internalType": "address", "name": "_winner", "type": "address"}
        ],
        "name": "resolveMatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_id", "type": "uint256"}],
        "name": "getTournament",
        "outputs": [
            {"internalType": "string", "name": "name", "type": "string"},
            {"internalType": "uint8", "name": "gameType", "type": "uint8"},
            {"internalType": "uint256", "name": "entryFee", "type": "uint256"},
            {"internalType": "uint256", "name": "maxPlayers", "type": "uint256"},
            {"internalType": "uint256", "name": "currentPlayers", "type": "uint256"},
            {"internalType": "address", "name": "winner", "type": "address"},
            {"internalType": "uint8", "name": "state", "type": "uint8"},
            {"internalType": "uint256", "name": "prizePool", "type": "uint256"},
            {"internalType": "uint256", "name": "currentRound", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_id", "type": "uint256"}],
        "name": "getTournamentMatches",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "tournamentId", "type": "uint256"},
                    {"internalType": "uint256", "name": "round", "type": "uint256"},
                    {"internalType": "uint256", "name": "matchIndex", "type": "uint256"},
                    {"internalType": "address", "name": "playerA", "type": "address"},
                    {"internalType": "address", "name": "playerB", "type": "address"},
                    {"internalType": "address", "name": "winner", "type": "address"},
                    {"internalType": "uint256", "name": "gameId", "type": "uint256"},
                    {"internalType": "bool", "name": "completed", "type": "bool"}
                ],
                "internalType": "struct Tournament.Match[]",
                "name": "",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "tournamentCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")


class GameClient:
    """Client for interacting with MonadArena smart contracts."""

    # Gas limit constants - Monad charges on gas_limit not gas_usage
    GAS_LIMIT_CREATE = 200_000
    GAS_LIMIT_JOIN = 150_000
    GAS_LIMIT_COMMIT = 100_000
    GAS_LIMIT_REVEAL = 250_000
    GAS_LIMIT_RESOLVE = 300_000

    def __init__(self, config: Config):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))

        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {config.rpc_url}")

        self.account = Account.from_key(config.private_key)
        self.address = self.account.address

        # Initialize contracts
        if config.game_arena_address and config.game_arena_address != "0x...":
            self.arena = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.game_arena_address),
                abi=GAME_ARENA_ABI,
            )
        else:
            self.arena = None

        if config.tournament_address and config.tournament_address != "0x...":
            self.tournament = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.tournament_address),
                abi=TOURNAMENT_ABI,
            )
        else:
            self.tournament = None

        logger.info(f"GameClient initialized: {self.address}")

    def _send_tx(self, tx_func, value: int = 0, gas_limit: int = 200_000) -> str:
        """Build, sign, and send a transaction. Returns tx hash."""
        nonce = self.w3.eth.get_transaction_count(self.address)
        gas_price = self.w3.eth.gas_price

        tx = tx_func.build_transaction({
            "from": self.address,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "value": value,
            "chainId": self.config.chain_id,
        })

        signed = self.w3.eth.account.sign_transaction(tx, self.config.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

        if receipt["status"] != 1:
            raise RuntimeError(f"Transaction failed: {tx_hash.hex()}")

        logger.info(f"TX confirmed: {tx_hash.hex()} (gas used: {receipt['gasUsed']})")
        return tx_hash.hex()

    def get_balance(self) -> float:
        """Get MON balance of our wallet."""
        balance_wei = self.w3.eth.get_balance(self.address)
        return float(self.w3.from_wei(balance_wei, "ether"))

    # --- Game Arena Functions ---

    def create_game(self, game_type: int, wager_mon: float) -> tuple[str, int]:
        """
        Create a new game with wager.
        Returns (tx_hash, game_id).
        """
        wager_wei = self.w3.to_wei(wager_mon, "ether")
        tx_func = self.arena.functions.createGame(game_type)
        tx_hash = self._send_tx(tx_func, value=wager_wei, gas_limit=self.GAS_LIMIT_CREATE)

        # Get game ID from event logs
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        game_id = self.arena.functions.gameCount().call() - 1

        logger.info(f"Game created: ID={game_id}, wager={wager_mon} MON")
        return tx_hash, game_id

    def join_game(self, game_id: int, wager_mon: float) -> str:
        """Join an existing game with matching wager."""
        wager_wei = self.w3.to_wei(wager_mon, "ether")
        tx_func = self.arena.functions.joinGame(game_id)
        tx_hash = self._send_tx(tx_func, value=wager_wei, gas_limit=self.GAS_LIMIT_JOIN)
        logger.info(f"Joined game {game_id}")
        return tx_hash

    def commit_move(self, game_id: int, move: bytes, salt: bytes) -> tuple[str, bytes]:
        """
        Commit a hashed move.
        Returns (tx_hash, commitment_hash).
        """
        commitment = self.w3.keccak(move + salt)
        tx_func = self.arena.functions.commitMove(game_id, commitment)
        tx_hash = self._send_tx(tx_func, gas_limit=self.GAS_LIMIT_COMMIT)
        logger.info(f"Move committed for game {game_id}")
        return tx_hash, commitment

    def reveal_move(self, game_id: int, move: bytes, salt: bytes) -> str:
        """Reveal a previously committed move."""
        salt_bytes32 = salt if len(salt) == 32 else self.w3.keccak(salt)
        tx_func = self.arena.functions.revealMove(game_id, move, salt_bytes32)
        tx_hash = self._send_tx(tx_func, gas_limit=self.GAS_LIMIT_REVEAL)
        logger.info(f"Move revealed for game {game_id}")
        return tx_hash

    def resolve_game(self, game_id: int, winner: str) -> str:
        """Resolve a game as oracle (owner only)."""
        tx_func = self.arena.functions.resolveGameByOracle(
            game_id, Web3.to_checksum_address(winner)
        )
        tx_hash = self._send_tx(tx_func, gas_limit=self.GAS_LIMIT_RESOLVE)
        logger.info(f"Game {game_id} resolved, winner: {winner}")
        return tx_hash

    def cancel_game(self, game_id: int) -> str:
        """Cancel a game (creator only, before join)."""
        tx_func = self.arena.functions.cancelGame(game_id)
        tx_hash = self._send_tx(tx_func, gas_limit=self.GAS_LIMIT_RESOLVE)
        logger.info(f"Game {game_id} cancelled")
        return tx_hash

    def get_game(self, game_id: int) -> dict:
        """Get game details."""
        game = self.arena.functions.getGame(game_id).call()
        return {
            "id": game[0],
            "game_type": game[1],
            "player_a": game[2],
            "player_b": game[3],
            "wager": float(self.w3.from_wei(game[4], "ether")),
            "state": game[5],
            "winner": game[6],
            "created_at": game[7],
            "resolved_at": game[8],
        }

    def get_player_stats(self, address: str) -> dict:
        """Get player statistics."""
        stats = self.arena.functions.getPlayerStats(
            Web3.to_checksum_address(address)
        ).call()
        return {
            "games_played": stats[0],
            "wins": stats[1],
            "losses": stats[2],
            "total_wagered": float(self.w3.from_wei(stats[3], "ether")),
            "total_won": float(self.w3.from_wei(stats[4], "ether")),
        }

    def get_game_count(self) -> int:
        """Get total number of games created."""
        return self.arena.functions.gameCount().call()

    # --- Tournament Functions ---

    def create_tournament(
        self, name: str, game_type: int, entry_fee_mon: float, max_players: int
    ) -> tuple[str, int]:
        """Create a tournament. Returns (tx_hash, tournament_id)."""
        entry_fee_wei = self.w3.to_wei(entry_fee_mon, "ether")
        tx_func = self.tournament.functions.createTournament(
            name, game_type, entry_fee_wei, max_players
        )
        tx_hash = self._send_tx(tx_func, gas_limit=self.GAS_LIMIT_CREATE)
        t_id = self.tournament.functions.tournamentCount().call() - 1
        logger.info(f"Tournament created: ID={t_id}, name={name}")
        return tx_hash, t_id

    def register_tournament(self, tournament_id: int, entry_fee_mon: float) -> str:
        """Register for a tournament."""
        fee_wei = self.w3.to_wei(entry_fee_mon, "ether")
        tx_func = self.tournament.functions.register(tournament_id)
        tx_hash = self._send_tx(tx_func, value=fee_wei, gas_limit=self.GAS_LIMIT_JOIN)
        logger.info(f"Registered for tournament {tournament_id}")
        return tx_hash

    def resolve_tournament_match(
        self, tournament_id: int, match_index: int, winner: str
    ) -> str:
        """Resolve a tournament match."""
        tx_func = self.tournament.functions.resolveMatch(
            tournament_id, match_index, Web3.to_checksum_address(winner)
        )
        tx_hash = self._send_tx(tx_func, gas_limit=self.GAS_LIMIT_RESOLVE)
        logger.info(f"Tournament {tournament_id} match {match_index} resolved")
        return tx_hash

    def get_tournament(self, tournament_id: int) -> dict:
        """Get tournament details."""
        t = self.tournament.functions.getTournament(tournament_id).call()
        return {
            "name": t[0],
            "game_type": t[1],
            "entry_fee": float(self.w3.from_wei(t[2], "ether")),
            "max_players": t[3],
            "current_players": t[4],
            "winner": t[5],
            "state": t[6],
            "prize_pool": float(self.w3.from_wei(t[7], "ether")),
            "current_round": t[8],
        }
