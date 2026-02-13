// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./GameArena.sol";

/**
 * @title Tournament
 * @notice Tournament management contract for MonadArena bracket-based competitions
 */
contract Tournament {
    enum TournamentState { Registration, Active, Completed, Cancelled }

    struct TournamentInfo {
        uint256 id;
        string name;
        GameArena.GameType gameType;
        uint256 entryFee;
        uint256 maxPlayers;
        uint256 currentPlayers;
        address[] players;
        address winner;
        TournamentState state;
        uint256 prizePool;
        uint256 createdAt;
        uint256 currentRound;
    }

    struct Match {
        uint256 tournamentId;
        uint256 round;
        uint256 matchIndex;
        address playerA;
        address playerB;
        address winner;
        uint256 gameId; // Reference to GameArena game
        bool completed;
    }

    GameArena public arena;
    address public owner;
    uint256 public tournamentCount;

    mapping(uint256 => TournamentInfo) public tournaments;
    mapping(uint256 => Match[]) public tournamentMatches;
    mapping(uint256 => mapping(address => bool)) public isRegistered;

    event TournamentCreated(uint256 indexed id, string name, uint256 entryFee, uint256 maxPlayers);
    event PlayerRegistered(uint256 indexed id, address indexed player);
    event TournamentStarted(uint256 indexed id);
    event MatchCreated(uint256 indexed tournamentId, uint256 round, address playerA, address playerB);
    event MatchResolved(uint256 indexed tournamentId, uint256 round, address indexed winner);
    event TournamentCompleted(uint256 indexed id, address indexed winner, uint256 prize);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address _arena) {
        arena = GameArena(payable(_arena));
        owner = msg.sender;
    }

    /**
     * @notice Create a new tournament
     * @param _name Tournament name
     * @param _gameType Game type for all matches
     * @param _entryFee Entry fee per player in MON
     * @param _maxPlayers Maximum number of players (must be power of 2, 2-16)
     */
    function createTournament(
        string memory _name,
        GameArena.GameType _gameType,
        uint256 _entryFee,
        uint256 _maxPlayers
    ) external returns (uint256) {
        require(_maxPlayers >= 2 && _maxPlayers <= 16, "2-16 players");
        require(
            _maxPlayers == 2 || _maxPlayers == 4 || _maxPlayers == 8 || _maxPlayers == 16,
            "Must be power of 2"
        );

        uint256 id = tournamentCount++;

        TournamentInfo storage t = tournaments[id];
        t.id = id;
        t.name = _name;
        t.gameType = _gameType;
        t.entryFee = _entryFee;
        t.maxPlayers = _maxPlayers;
        t.state = TournamentState.Registration;
        t.createdAt = block.timestamp;

        emit TournamentCreated(id, _name, _entryFee, _maxPlayers);
        return id;
    }

    /**
     * @notice Register for a tournament
     * @param _tournamentId Tournament ID
     */
    function register(uint256 _tournamentId) external payable {
        TournamentInfo storage t = tournaments[_tournamentId];
        require(t.state == TournamentState.Registration, "Not in registration");
        require(t.currentPlayers < t.maxPlayers, "Tournament full");
        require(!isRegistered[_tournamentId][msg.sender], "Already registered");
        require(msg.value == t.entryFee, "Wrong entry fee");

        t.players.push(msg.sender);
        t.currentPlayers++;
        t.prizePool += msg.value;
        isRegistered[_tournamentId][msg.sender] = true;

        emit PlayerRegistered(_tournamentId, msg.sender);

        // Auto-start when full
        if (t.currentPlayers == t.maxPlayers) {
            _startTournament(_tournamentId);
        }
    }

    function _startTournament(uint256 _tournamentId) internal {
        TournamentInfo storage t = tournaments[_tournamentId];
        t.state = TournamentState.Active;
        t.currentRound = 1;

        // Create first round matches
        for (uint256 i = 0; i < t.currentPlayers; i += 2) {
            Match memory m = Match({
                tournamentId: _tournamentId,
                round: 1,
                matchIndex: i / 2,
                playerA: t.players[i],
                playerB: t.players[i + 1],
                winner: address(0),
                gameId: 0,
                completed: false
            });
            tournamentMatches[_tournamentId].push(m);
            emit MatchCreated(_tournamentId, 1, t.players[i], t.players[i + 1]);
        }

        emit TournamentStarted(_tournamentId);
    }

    /**
     * @notice Resolve a tournament match (called by oracle/owner after off-chain game)
     * @param _tournamentId Tournament ID
     * @param _matchIndex Index in the matches array
     * @param _winner Winner address
     */
    function resolveMatch(
        uint256 _tournamentId,
        uint256 _matchIndex,
        address _winner
    ) external onlyOwner {
        TournamentInfo storage t = tournaments[_tournamentId];
        require(t.state == TournamentState.Active, "Tournament not active");

        Match storage m = tournamentMatches[_tournamentId][_matchIndex];
        require(!m.completed, "Match already resolved");
        require(
            _winner == m.playerA || _winner == m.playerB,
            "Winner must be a player in this match"
        );

        m.winner = _winner;
        m.completed = true;

        emit MatchResolved(_tournamentId, m.round, _winner);

        // Check if current round is complete
        _checkRoundComplete(_tournamentId);
    }

    function _checkRoundComplete(uint256 _tournamentId) internal {
        TournamentInfo storage t = tournaments[_tournamentId];
        Match[] storage matches = tournamentMatches[_tournamentId];

        // Count completed matches in current round
        uint256 roundMatches = 0;
        uint256 completedMatches = 0;
        address[] memory winners = new address[](t.maxPlayers);
        uint256 winnerCount = 0;

        for (uint256 i = 0; i < matches.length; i++) {
            if (matches[i].round == t.currentRound) {
                roundMatches++;
                if (matches[i].completed) {
                    completedMatches++;
                    winners[winnerCount++] = matches[i].winner;
                }
            }
        }

        if (completedMatches == roundMatches && roundMatches > 0) {
            if (winnerCount == 1) {
                // Tournament complete
                _completeTournament(_tournamentId, winners[0]);
            } else {
                // Create next round
                t.currentRound++;
                for (uint256 i = 0; i < winnerCount; i += 2) {
                    Match memory m = Match({
                        tournamentId: _tournamentId,
                        round: t.currentRound,
                        matchIndex: i / 2,
                        playerA: winners[i],
                        playerB: winners[i + 1],
                        winner: address(0),
                        gameId: 0,
                        completed: false
                    });
                    matches.push(m);
                    emit MatchCreated(_tournamentId, t.currentRound, winners[i], winners[i + 1]);
                }
            }
        }
    }

    function _completeTournament(uint256 _tournamentId, address _winner) internal {
        TournamentInfo storage t = tournaments[_tournamentId];
        t.winner = _winner;
        t.state = TournamentState.Completed;

        uint256 fee = (t.prizePool * 100) / 10000; // 1% platform fee
        uint256 prize = t.prizePool - fee;

        (bool success, ) = payable(_winner).call{value: prize}("");
        require(success, "Prize payout failed");

        emit TournamentCompleted(_tournamentId, _winner, prize);
    }

    /**
     * @notice Cancel tournament and refund all players
     * @param _tournamentId Tournament ID
     */
    function cancelTournament(uint256 _tournamentId) external onlyOwner {
        TournamentInfo storage t = tournaments[_tournamentId];
        require(
            t.state == TournamentState.Registration || t.state == TournamentState.Active,
            "Cannot cancel"
        );

        t.state = TournamentState.Cancelled;

        // Refund all players
        for (uint256 i = 0; i < t.players.length; i++) {
            (bool success, ) = payable(t.players[i]).call{value: t.entryFee}("");
            require(success, "Refund failed");
        }
    }

    // View functions

    function getTournament(uint256 _id) external view returns (
        string memory name,
        GameArena.GameType gameType,
        uint256 entryFee,
        uint256 maxPlayers,
        uint256 currentPlayers,
        address winner,
        TournamentState state,
        uint256 prizePool,
        uint256 currentRound
    ) {
        TournamentInfo storage t = tournaments[_id];
        return (
            t.name, t.gameType, t.entryFee, t.maxPlayers,
            t.currentPlayers, t.winner, t.state, t.prizePool, t.currentRound
        );
    }

    function getTournamentPlayers(uint256 _id) external view returns (address[] memory) {
        return tournaments[_id].players;
    }

    function getTournamentMatches(uint256 _id) external view returns (Match[] memory) {
        return tournamentMatches[_id];
    }

    receive() external payable {}
}
