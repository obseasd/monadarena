// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title GameArena
 * @notice Main gaming arena contract for MonadArena - manages games, wagers, and payouts on Monad
 * @dev Uses commit-reveal pattern for fair move submission. Supports multiple game types.
 */
contract GameArena {
    enum GameState { Created, Active, CommitPhase, RevealPhase, Resolved, Cancelled }
    enum GameType { Poker, Auction }

    struct Game {
        uint256 id;
        GameType gameType;
        address playerA;
        address playerB;
        uint256 wager;
        GameState state;
        address winner;
        uint256 createdAt;
        uint256 resolvedAt;
        bytes32 commitA;
        bytes32 commitB;
        bytes revealA;
        bytes revealB;
    }

    struct PlayerStats {
        uint256 gamesPlayed;
        uint256 wins;
        uint256 losses;
        uint256 totalWagered;
        uint256 totalWon;
    }

    uint256 public gameCount;
    uint256 public constant MIN_WAGER = 0.001 ether;   // 0.001 MON
    uint256 public constant MAX_WAGER = 100 ether;      // 100 MON
    uint256 public constant COMMIT_TIMEOUT = 300;        // 5 minutes
    uint256 public constant REVEAL_TIMEOUT = 300;        // 5 minutes
    uint256 public constant PLATFORM_FEE_BPS = 100;      // 1%

    address public owner;

    mapping(uint256 => Game) public games;
    mapping(address => PlayerStats) public playerStats;
    mapping(address => uint256[]) public playerGames;

    event GameCreated(uint256 indexed gameId, address indexed playerA, GameType gameType, uint256 wager);
    event GameJoined(uint256 indexed gameId, address indexed playerB);
    event MoveCommitted(uint256 indexed gameId, address indexed player);
    event MoveRevealed(uint256 indexed gameId, address indexed player);
    event GameResolved(uint256 indexed gameId, address indexed winner, uint256 payout);
    event GameCancelled(uint256 indexed gameId);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Create a new game with a MON wager
     * @param _gameType The type of game (Poker or Auction)
     * @return gameId The ID of the created game
     */
    function createGame(GameType _gameType) external payable returns (uint256) {
        require(msg.value >= MIN_WAGER, "Wager too low");
        require(msg.value <= MAX_WAGER, "Wager too high");

        uint256 gameId = gameCount++;
        games[gameId] = Game({
            id: gameId,
            gameType: _gameType,
            playerA: msg.sender,
            playerB: address(0),
            wager: msg.value,
            state: GameState.Created,
            winner: address(0),
            createdAt: block.timestamp,
            resolvedAt: 0,
            commitA: bytes32(0),
            commitB: bytes32(0),
            revealA: "",
            revealB: ""
        });

        playerGames[msg.sender].push(gameId);
        emit GameCreated(gameId, msg.sender, _gameType, msg.value);
        return gameId;
    }

    /**
     * @notice Join an existing game with matching wager
     * @param _gameId The game ID to join
     */
    function joinGame(uint256 _gameId) external payable {
        Game storage game = games[_gameId];
        require(game.state == GameState.Created, "Game not open");
        require(msg.sender != game.playerA, "Cannot join own game");
        require(msg.value == game.wager, "Wager mismatch");

        game.playerB = msg.sender;
        game.state = GameState.CommitPhase;
        playerGames[msg.sender].push(_gameId);
        emit GameJoined(_gameId, msg.sender);
    }

    /**
     * @notice Commit a hashed move (commit-reveal pattern)
     * @param _gameId The game ID
     * @param _commitment keccak256(abi.encodePacked(move, salt))
     */
    function commitMove(uint256 _gameId, bytes32 _commitment) external {
        Game storage game = games[_gameId];
        require(
            game.state == GameState.CommitPhase || game.state == GameState.Active,
            "Not in commit phase"
        );
        require(
            msg.sender == game.playerA || msg.sender == game.playerB,
            "Not a player"
        );

        if (msg.sender == game.playerA) {
            require(game.commitA == bytes32(0), "Already committed");
            game.commitA = _commitment;
        } else {
            require(game.commitB == bytes32(0), "Already committed");
            game.commitB = _commitment;
        }

        if (game.commitA != bytes32(0) && game.commitB != bytes32(0)) {
            game.state = GameState.RevealPhase;
        }

        emit MoveCommitted(_gameId, msg.sender);
    }

    /**
     * @notice Reveal a previously committed move
     * @param _gameId The game ID
     * @param _move The actual move bytes
     * @param _salt The salt used in the commitment
     */
    function revealMove(uint256 _gameId, bytes calldata _move, bytes32 _salt) external {
        Game storage game = games[_gameId];
        require(game.state == GameState.RevealPhase, "Not in reveal phase");
        require(
            msg.sender == game.playerA || msg.sender == game.playerB,
            "Not a player"
        );

        bytes32 commitment = keccak256(abi.encodePacked(_move, _salt));

        if (msg.sender == game.playerA) {
            require(commitment == game.commitA, "Invalid reveal A");
            game.revealA = _move;
        } else {
            require(commitment == game.commitB, "Invalid reveal B");
            game.revealB = _move;
        }

        if (game.revealA.length > 0 && game.revealB.length > 0) {
            _resolveGame(_gameId);
        }

        emit MoveRevealed(_gameId, msg.sender);
    }

    /**
     * @notice Resolve a game by the owner/oracle after off-chain game logic
     * @dev Used when game resolution is determined off-chain (poker hands, auction bids)
     * @param _gameId The game ID
     * @param _winner The winner's address
     */
    function resolveGameByOracle(uint256 _gameId, address _winner) external onlyOwner {
        Game storage game = games[_gameId];
        require(
            game.state == GameState.CommitPhase ||
            game.state == GameState.RevealPhase ||
            game.state == GameState.Active,
            "Game not resolvable"
        );
        require(
            _winner == game.playerA || _winner == game.playerB,
            "Winner must be a player"
        );

        game.state = GameState.Resolved;
        game.resolvedAt = block.timestamp;
        game.winner = _winner;

        address loser = _winner == game.playerA ? game.playerB : game.playerA;

        uint256 totalPot = game.wager * 2;
        uint256 fee = (totalPot * PLATFORM_FEE_BPS) / 10000;
        uint256 payout = totalPot - fee;

        _updateStats(_winner, loser, game.wager);

        (bool success, ) = payable(_winner).call{value: payout}("");
        require(success, "Payout failed");

        emit GameResolved(_gameId, _winner, payout);
    }

    function _resolveGame(uint256 _gameId) internal {
        Game storage game = games[_gameId];
        game.state = GameState.Resolved;
        game.resolvedAt = block.timestamp;

        address winner = _determineWinner(game);
        game.winner = winner;

        address loser = winner == game.playerA ? game.playerB : game.playerA;

        uint256 totalPot = game.wager * 2;
        uint256 fee = (totalPot * PLATFORM_FEE_BPS) / 10000;
        uint256 payout = totalPot - fee;

        _updateStats(winner, loser, game.wager);

        (bool success, ) = payable(winner).call{value: payout}("");
        require(success, "Payout failed");

        emit GameResolved(_gameId, winner, payout);
    }

    function _determineWinner(Game storage game) internal view returns (address) {
        // Decode moves and compare - for commit-reveal based games
        bytes32 moveHashA = keccak256(game.revealA);
        bytes32 moveHashB = keccak256(game.revealB);

        if (uint256(moveHashA) > uint256(moveHashB)) return game.playerA;
        if (uint256(moveHashB) > uint256(moveHashA)) return game.playerB;
        return game.playerA; // Tie goes to creator
    }

    function _updateStats(address winner, address loser, uint256 wager) internal {
        playerStats[winner].gamesPlayed++;
        playerStats[winner].wins++;
        playerStats[winner].totalWagered += wager;
        playerStats[winner].totalWon += wager * 2;

        playerStats[loser].gamesPlayed++;
        playerStats[loser].losses++;
        playerStats[loser].totalWagered += wager;
    }

    /**
     * @notice Cancel a game that hasn't been joined yet
     * @param _gameId The game ID to cancel
     */
    function cancelGame(uint256 _gameId) external {
        Game storage game = games[_gameId];
        require(game.state == GameState.Created, "Game not cancellable");
        require(msg.sender == game.playerA, "Not game creator");

        game.state = GameState.Cancelled;
        (bool success, ) = payable(game.playerA).call{value: game.wager}("");
        require(success, "Refund failed");

        emit GameCancelled(_gameId);
    }

    /**
     * @notice Claim timeout if opponent fails to commit/reveal in time
     * @param _gameId The game ID
     */
    function claimTimeout(uint256 _gameId) external {
        Game storage game = games[_gameId];
        require(
            msg.sender == game.playerA || msg.sender == game.playerB,
            "Not a player"
        );

        if (game.state == GameState.CommitPhase) {
            require(
                block.timestamp > game.createdAt + COMMIT_TIMEOUT,
                "Timeout not reached"
            );
            // Refund both players if neither committed, or reward the committer
            if (game.commitA != bytes32(0) && game.commitB == bytes32(0)) {
                _forceResolve(_gameId, game.playerA);
            } else if (game.commitB != bytes32(0) && game.commitA == bytes32(0)) {
                _forceResolve(_gameId, game.playerB);
            } else {
                // Neither committed - refund both
                game.state = GameState.Cancelled;
                (bool s1, ) = payable(game.playerA).call{value: game.wager}("");
                (bool s2, ) = payable(game.playerB).call{value: game.wager}("");
                require(s1 && s2, "Refund failed");
                emit GameCancelled(_gameId);
            }
        } else if (game.state == GameState.RevealPhase) {
            require(
                block.timestamp > game.createdAt + COMMIT_TIMEOUT + REVEAL_TIMEOUT,
                "Timeout not reached"
            );
            // Reward the player who revealed
            if (game.revealA.length > 0 && game.revealB.length == 0) {
                _forceResolve(_gameId, game.playerA);
            } else if (game.revealB.length > 0 && game.revealA.length == 0) {
                _forceResolve(_gameId, game.playerB);
            }
        }
    }

    function _forceResolve(uint256 _gameId, address _winner) internal {
        Game storage game = games[_gameId];
        game.state = GameState.Resolved;
        game.resolvedAt = block.timestamp;
        game.winner = _winner;

        address loser = _winner == game.playerA ? game.playerB : game.playerA;
        uint256 totalPot = game.wager * 2;
        uint256 fee = (totalPot * PLATFORM_FEE_BPS) / 10000;
        uint256 payout = totalPot - fee;

        _updateStats(_winner, loser, game.wager);

        (bool success, ) = payable(_winner).call{value: payout}("");
        require(success, "Payout failed");

        emit GameResolved(_gameId, _winner, payout);
    }

    // View functions

    function getGame(uint256 _gameId) external view returns (Game memory) {
        return games[_gameId];
    }

    function getPlayerGames(address _player) external view returns (uint256[] memory) {
        return playerGames[_player];
    }

    function getPlayerStats(address _player) external view returns (PlayerStats memory) {
        return playerStats[_player];
    }

    function getContractBalance() external view returns (uint256) {
        return address(this).balance;
    }

    // Allow contract to receive MON
    receive() external payable {}
}
