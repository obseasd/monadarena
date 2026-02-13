const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GameArena", function () {
  let arena, tournament;
  let owner, playerA, playerB, playerC, playerD;
  const WAGER = ethers.parseEther("0.01"); // 0.01 MON

  beforeEach(async function () {
    [owner, playerA, playerB, playerC, playerD] = await ethers.getSigners();

    const GameArena = await ethers.getContractFactory("GameArena");
    arena = await GameArena.deploy();
    await arena.waitForDeployment();

    const Tournament = await ethers.getContractFactory("Tournament");
    tournament = await Tournament.deploy(await arena.getAddress());
    await tournament.waitForDeployment();
  });

  describe("Game Creation", function () {
    it("Should create a game with valid wager", async function () {
      const tx = await arena.connect(playerA).createGame(0, { value: WAGER });
      await tx.wait();

      const game = await arena.getGame(0);
      expect(game.playerA).to.equal(playerA.address);
      expect(game.wager).to.equal(WAGER);
      expect(game.state).to.equal(0); // Created
    });

    it("Should reject wager below minimum", async function () {
      await expect(
        arena.connect(playerA).createGame(0, { value: ethers.parseEther("0.0001") })
      ).to.be.revertedWith("Wager too low");
    });

    it("Should reject wager above maximum", async function () {
      await expect(
        arena.connect(playerA).createGame(0, { value: ethers.parseEther("101") })
      ).to.be.revertedWith("Wager too high");
    });

    it("Should emit GameCreated event", async function () {
      await expect(arena.connect(playerA).createGame(0, { value: WAGER }))
        .to.emit(arena, "GameCreated")
        .withArgs(0, playerA.address, 0, WAGER);
    });
  });

  describe("Game Joining", function () {
    beforeEach(async function () {
      await arena.connect(playerA).createGame(0, { value: WAGER });
    });

    it("Should allow another player to join", async function () {
      await arena.connect(playerB).joinGame(0, { value: WAGER });
      const game = await arena.getGame(0);
      expect(game.playerB).to.equal(playerB.address);
      expect(game.state).to.equal(2); // CommitPhase
    });

    it("Should reject self-join", async function () {
      await expect(
        arena.connect(playerA).joinGame(0, { value: WAGER })
      ).to.be.revertedWith("Cannot join own game");
    });

    it("Should reject wrong wager amount", async function () {
      await expect(
        arena.connect(playerB).joinGame(0, { value: ethers.parseEther("0.02") })
      ).to.be.revertedWith("Wager mismatch");
    });
  });

  describe("Commit-Reveal", function () {
    const moveA = ethers.toUtf8Bytes("rock");
    const moveB = ethers.toUtf8Bytes("paper");
    const saltA = ethers.id("saltA");
    const saltB = ethers.id("saltB");
    let commitA, commitB;

    beforeEach(async function () {
      await arena.connect(playerA).createGame(0, { value: WAGER });
      await arena.connect(playerB).joinGame(0, { value: WAGER });

      commitA = ethers.keccak256(ethers.solidityPacked(["bytes", "bytes32"], [moveA, saltA]));
      commitB = ethers.keccak256(ethers.solidityPacked(["bytes", "bytes32"], [moveB, saltB]));
    });

    it("Should allow both players to commit", async function () {
      await arena.connect(playerA).commitMove(0, commitA);
      await arena.connect(playerB).commitMove(0, commitB);

      const game = await arena.getGame(0);
      expect(game.state).to.equal(3); // RevealPhase
    });

    it("Should resolve after both reveals", async function () {
      await arena.connect(playerA).commitMove(0, commitA);
      await arena.connect(playerB).commitMove(0, commitB);

      await arena.connect(playerA).revealMove(0, moveA, saltA);
      await arena.connect(playerB).revealMove(0, moveB, saltB);

      const game = await arena.getGame(0);
      expect(game.state).to.equal(4); // Resolved
      expect(game.winner).to.not.equal(ethers.ZeroAddress);
    });
  });

  describe("Oracle Resolution", function () {
    beforeEach(async function () {
      await arena.connect(playerA).createGame(0, { value: WAGER });
      await arena.connect(playerB).joinGame(0, { value: WAGER });
    });

    it("Should allow owner to resolve game", async function () {
      const balanceBefore = await ethers.provider.getBalance(playerA.address);

      await arena.connect(owner).resolveGameByOracle(0, playerA.address);

      const game = await arena.getGame(0);
      expect(game.state).to.equal(4); // Resolved
      expect(game.winner).to.equal(playerA.address);

      const balanceAfter = await ethers.provider.getBalance(playerA.address);
      expect(balanceAfter).to.be.greaterThan(balanceBefore);
    });

    it("Should reject non-owner oracle call", async function () {
      await expect(
        arena.connect(playerA).resolveGameByOracle(0, playerA.address)
      ).to.be.revertedWith("Not owner");
    });
  });

  describe("Game Cancellation", function () {
    it("Should allow creator to cancel unjoined game", async function () {
      await arena.connect(playerA).createGame(0, { value: WAGER });

      const balanceBefore = await ethers.provider.getBalance(playerA.address);
      await arena.connect(playerA).cancelGame(0);
      const balanceAfter = await ethers.provider.getBalance(playerA.address);

      const game = await arena.getGame(0);
      expect(game.state).to.equal(5); // Cancelled

      // Balance should increase (minus gas)
      expect(balanceAfter).to.be.greaterThan(balanceBefore - ethers.parseEther("0.001"));
    });
  });

  describe("Player Stats", function () {
    it("Should track player stats after game resolution", async function () {
      await arena.connect(playerA).createGame(0, { value: WAGER });
      await arena.connect(playerB).joinGame(0, { value: WAGER });
      await arena.connect(owner).resolveGameByOracle(0, playerA.address);

      const statsA = await arena.getPlayerStats(playerA.address);
      expect(statsA.gamesPlayed).to.equal(1);
      expect(statsA.wins).to.equal(1);

      const statsB = await arena.getPlayerStats(playerB.address);
      expect(statsB.gamesPlayed).to.equal(1);
      expect(statsB.losses).to.equal(1);
    });
  });

  describe("Tournament", function () {
    it("Should create and run a 4-player tournament", async function () {
      const ENTRY_FEE = ethers.parseEther("0.01");

      // Create tournament
      await tournament.createTournament("Test Tournament", 0, ENTRY_FEE, 4);

      // Register 4 players
      await tournament.connect(playerA).register(0, { value: ENTRY_FEE });
      await tournament.connect(playerB).register(0, { value: ENTRY_FEE });
      await tournament.connect(playerC).register(0, { value: ENTRY_FEE });
      await tournament.connect(playerD).register(0, { value: ENTRY_FEE });

      // Tournament should auto-start
      const t = await tournament.getTournament(0);
      expect(t.state).to.equal(1); // Active

      // Resolve first round matches
      const matches = await tournament.getTournamentMatches(0);
      expect(matches.length).to.equal(2); // 2 matches in round 1

      // Resolve match 0: playerA wins
      await tournament.connect(owner).resolveMatch(0, 0, playerA.address);
      // Resolve match 1: playerC wins
      await tournament.connect(owner).resolveMatch(0, 1, playerC.address);

      // Now finals should be created
      const matchesAfterR1 = await tournament.getTournamentMatches(0);
      expect(matchesAfterR1.length).to.equal(3); // 2 round1 + 1 final

      // Resolve finals: playerA wins tournament
      await tournament.connect(owner).resolveMatch(0, 2, playerA.address);

      const tFinal = await tournament.getTournament(0);
      expect(tFinal.state).to.equal(2); // Completed
      expect(tFinal.winner).to.equal(playerA.address);
    });
  });
});
