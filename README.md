# MonadArena - AI Gaming Arena on Monad

AI-powered competitive gaming arena with LLM strategic agents, on-chain wagering, and tournament brackets on the Monad blockchain.

**Built for the [Moltiverse Hackathon](https://moltiverse.dev/) - Gaming Arena Agent Bounty ($10K)**

## What is MonadArena?

MonadArena is a fully autonomous AI gaming platform where LLM-powered agents compete in **poker**, **blind auctions**, and **RPG battles** with real MON token wagers. Every strategic decision - when to bluff, how much to bid, which ability to cast - is made by Claude AI with chain-of-thought reasoning, not hardcoded heuristics.

### Key Features

- **3 Game Types**: Texas Hold'em Poker + Strategic Blind Auctions + RPG Battle Arena
- **LLM-Powered Strategy**: Every decision goes through Claude with step-by-step reasoning
- **On-Chain Wagering**: Smart contract escrow with automatic payouts on Monad
- **Live Web UI**: Uniswap-style dashboard with poker table visualization & real-time match feed
- **Tournament Mode**: Single-elimination bracket tournaments with live bracket visualization
- **Spectator Mode**: Auto-populating poker table during demo - watch AI agents play in real time
- **AI Trash Talk**: LLM-generated pre-match trash talk with personality-driven one-liners
- **Opponent Modeling**: Agents track opponent patterns and adapt over time
- **Bankroll Management**: Kelly Criterion-inspired risk management
- **Bluff Detection**: Track and detect bluffs across matches
- **4 Agent Personalities**: Aggressive, Conservative, Balanced, Adaptive - each with unique strategy

## Live Demo

Launch the web UI to see everything in action:

```bash
python web/app.py
# Open http://localhost:5000
```

Features in the Web UI:
- **Quick Poker**: Run a heads-up poker match between two AI agents
- **Quick RPG**: Watch AI agents battle with spells, swords, and strategy
- **Tournament**: 4-agent single-elimination bracket with semi-finals and grand final
- **Full Demo**: 6 round-robin matches + auction + RPG + tournament with live spectator mode
- **Leaderboard**: Real-time agent rankings with P&L, win rate, and bluff stats
- **Match History**: Detailed log of every match with hand details, community cards, and results

## Architecture

```
Agent (LLM Strategy) -> Game Engine (Poker/Auction/RPG) -> Arena Manager -> Smart Contracts (Monad)
         |                          |                            |
   Opponent Model            Hand Evaluation              On-Chain Settlement
   Bankroll Mgmt             Bid Resolution               Tournament Brackets
   Trash Talk AI             RPG Ability System            Live Web UI
```

### Smart Contracts (Solidity)
- **GameArena.sol**: Game creation, wager escrow, commit-reveal, oracle resolution, payouts
- **Tournament.sol**: Tournament brackets, registration, match progression, prize distribution
- Deployed on Monad Testnet:
  - GameArena: `0xBFd5542a97E96D8F2E2D1A39E839c7A15bA731E1`
  - Tournament: `0x5e3Fe22590C61818e13CB3F1f75a809A1b014BC3`

### AI Agent (Python)
- **StrategyEngine**: LLM-powered decision making with structured JSON output + trash talk generation
- **OpponentModel**: Tracks aggression, tightness, bluff frequency, play style classification
- **BankrollManager**: Kelly Criterion bet sizing, stop-loss, risk levels
- **GameClient**: Web3 interaction with Monad contracts

### Game Engines (Python)
- **PokerGame**: Heads-up Texas Hold'em with full hand evaluation (all 10 rankings)
- **AuctionGame**: Multi-round blind bidding with value estimation
- **RPGBattleGame**: Turn-based RPG with 4 classes, abilities, buffs/debuffs, DoTs, and MP management

### Web UI (Flask + Vanilla JS)
- **Uniswap-style SPA**: Dark theme with Monad purple (#6D51FE) accents
- **Poker Table Overlay**: Animated card display with community cards and player hands
- **Tournament Bracket**: Live CSS bracket visualization with winner highlighting
- **Spectator Mode**: Auto-polling for completed matches, auto-display poker table
- **Trash Talk Bubbles**: Speech bubbles showing AI-generated pre-match banter

## RPG Battle System

4 character classes with unique abilities:

| Class | HP | MP | ATK | DEF | SPD | Specialty |
|-------|----|----|-----|-----|-----|-----------|
| Warrior | 120 | 40 | 18 | 14 | 8 | High HP, powerful physical attacks |
| Mage | 80 | 100 | 8 | 8 | 12 | Devastating spells, AoE damage |
| Rogue | 90 | 60 | 14 | 8 | 18 | Speed, poison, critical strikes |
| Healer | 100 | 80 | 10 | 12 | 10 | Sustain, buffs, regeneration |

Each class has 6+ abilities including attacks, heals, buffs, debuffs, and DoTs. The LLM chooses abilities strategically based on both fighters' HP/MP, active buffs, and opponent patterns.

Agent personalities map to classes: Aggressive→Warrior, Conservative→Healer, Balanced→Mage, Adaptive→Rogue.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- An Anthropic API key

### Setup

```bash
# Clone
git clone https://github.com/obseasd/monadarena
cd monadarena

# Python dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your keys

# Smart contracts
cd contracts
npm install
npx hardhat compile
```

### Deploy Contracts

```bash
cd contracts
npx hardhat run scripts/deploy.js --network monadTestnet
# Update .env with deployed addresses
```

### Run Web UI

```bash
python web/app.py
# Open http://localhost:5000
```

### Run CLI Demo

```bash
# Full interactive demo
python demo.py

# CLI commands
python cli.py play --matches 5 --game poker --wager 0.05
python cli.py play --game rpg --wager 0.05
python cli.py tournament --players 4 --game poker
python cli.py status
```

### Run Tests

```bash
pytest tests/ -v
# 100 tests covering poker, auction, RPG, agent, bankroll, opponent model
```

## How It Works

### 1. LLM Strategic Decisions

Every poker/auction/RPG decision is made by the LLM with full context:

```
POKER EXAMPLE:
- Your hand: Ah, Kd
- Community cards: Jh, Tc, 2s
- Pot: 0.05 MON, To call: 0.02 MON
- Opponent style: loose-aggressive, bluff freq 30%
- Decision: CALL (pot odds 3.5:1, need 22% equity, have ~35%)

RPG EXAMPLE:
- Your Fighter: Mage (HP:60/80, MP:45/100)
- Enemy: Warrior (HP:90/120, MP:10/40)
- Active effects: Enemy has -3 ATK debuff (2 turns)
- Decision: FIREBALL (enemy low on MP, can't heal, finish them)
```

### 2. Opponent Modeling

Agents classify opponents into styles and adapt:
- **Loose-Aggressive**: High raise%, low fold% → Play tighter, trap with strong hands
- **Tight-Passive**: High fold%, low raise% → Bluff more, steal blinds
- **Tight-Aggressive**: Selective but powerful → Respect raises, don't bluff into strength
- **Loose-Passive**: Calls everything → Value bet relentlessly

### 3. Bankroll Management

Kelly Criterion ensures optimal bet sizing:
```
Kelly fraction = (win_prob * odds - loss_prob) / odds
Bet size = Half-Kelly * bankroll  (half for safety)
```
Plus stop-loss at 30% of initial bankroll.

### 4. AI Trash Talk

Before tournament matches, agents generate personality-driven trash talk:
- **Aggressive**: "Your chips are already mine. I hope you said goodbye to your MON."
- **Conservative**: "I've calculated every outcome. None of them end well for you."
- **Balanced**: "May the best algorithm win... which statistically speaking, is mine."
- **Adaptive**: "I've been watching your patterns. You're more predictable than you think."

### 5. On-Chain Settlement

All wagers settled through smart contracts on Monad:
1. Create game with MON wager (escrowed in contract)
2. Opponent joins with matching wager
3. Game plays out off-chain with LLM decisions
4. Oracle resolves winner on-chain
5. Winner receives 99% of pot (1% platform fee)

Monad's 400ms block time enables near-instant settlement.

## Project Structure

```
monadarena/
  contracts/              # Solidity smart contracts
    src/
      GameArena.sol       # Main arena contract
      Tournament.sol      # Tournament brackets
    scripts/              # Deploy scripts
    test/                 # Contract tests
  agent/                  # AI agent modules
    strategy_engine.py    # LLM decision engine + trash talk
    opponent_model.py     # Opponent tracking & classification
    bankroll.py           # Kelly Criterion risk management
    game_client.py        # Monad contract interaction
    config.py             # Configuration
  games/                  # Game implementations
    poker.py              # Texas Hold'em engine (10 hand rankings)
    auction.py            # Blind auction engine
    rpg_battle.py         # RPG battle engine (4 classes, abilities)
    base.py               # Game interface
  arena/                  # Arena management
    manager.py            # Match orchestration + bluff detection
    tournament.py         # Tournament brackets
    matchmaker.py         # Auto-matching
  web/                    # Web UI
    app.py                # Flask server + API endpoints
    templates/
      index.html          # SPA with poker table, bracket, spectator
    static/               # Assets (logos, favicons)
  tests/                  # 100 tests
    test_poker.py         # Poker engine tests
    test_auction.py       # Auction engine tests
    test_rpg_battle.py    # RPG battle tests
    test_agent.py         # Strategy engine tests
    test_bankroll.py      # Bankroll management tests
    test_opponent.py      # Opponent model tests
  demo.py                 # Interactive demo
  cli.py                  # CLI interface
```

## Bounty Requirements Checklist

| Requirement | Status | Details |
|-------------|--------|---------|
| At least 1 game type | ✅ | 3 games (Poker + Auction + RPG Battle) |
| Wagering with real tokens | ✅ | MON via smart contracts on Monad testnet |
| LLM-powered decisions (not heuristics) | ✅ | Claude with chain-of-thought reasoning |
| Smart contract for wagers/payouts | ✅ | GameArena.sol + Tournament.sol (deployed) |
| 5+ matches vs different opponents | ✅ | Round-robin + tournament system |
| Multiple game types (bonus) | ✅ | 3 game types |
| Adaptive strategy (bonus) | ✅ | Opponent modeling + style classification |
| Bluffing capability (bonus) | ✅ | LLM bluff detection & execution |
| Tournament system (bonus) | ✅ | Single-elimination brackets with live UI |
| Bankroll management (bonus) | ✅ | Kelly Criterion + stop-loss |
| Web UI (bonus) | ✅ | Full dashboard with poker table & bracket |
| AI personality (bonus) | ✅ | 4 personalities + trash talk |

## Tech Stack

- **Python 3.12** - Agent, game engines, CLI, web server
- **Flask** - Web UI backend
- **Solidity 0.8.24** - Smart contracts
- **Anthropic Claude API** - LLM strategic decisions
- **web3.py** - Blockchain interaction
- **Hardhat** - Contract compilation, testing, deployment
- **Monad** - 400ms blocks, 10K TPS, EVM compatible

## Network Info

| | Testnet | Mainnet |
|--|---------|---------|
| RPC | https://testnet-rpc.monad.xyz | https://rpc.monad.xyz |
| Chain ID | 10143 | 143 |
| Explorer | testnet.monadscan.com | monadscan.com |

## Deployed Contracts

- **GameArena**: [`0xBFd5542a97E96D8F2E2D1A39E839c7A15bA731E1`](https://testnet.monadscan.com/address/0xBFd5542a97E96D8F2E2D1A39E839c7A15bA731E1)
- **Tournament**: [`0x5e3Fe22590C61818e13CB3F1f75a809A1b014BC3`](https://testnet.monadscan.com/address/0x5e3Fe22590C61818e13CB3F1f75a809A1b014BC3)

## License

MIT
