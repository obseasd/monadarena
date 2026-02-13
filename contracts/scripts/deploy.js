const hre = require("hardhat");

async function main() {
  console.log("Deploying MonadArena contracts to Monad Testnet...");
  console.log("Network:", hre.network.name);

  const [deployer] = await hre.ethers.getSigners();
  console.log("Deployer:", deployer.address);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Balance:", hre.ethers.formatEther(balance), "MON");

  // Deploy GameArena
  console.log("\n1. Deploying GameArena...");
  const GameArena = await hre.ethers.getContractFactory("GameArena");
  const arena = await GameArena.deploy();
  await arena.waitForDeployment();
  const arenaAddress = await arena.getAddress();
  console.log("GameArena deployed to:", arenaAddress);

  // Deploy Tournament
  console.log("\n2. Deploying Tournament...");
  const Tournament = await hre.ethers.getContractFactory("Tournament");
  const tournament = await Tournament.deploy(arenaAddress);
  await tournament.waitForDeployment();
  const tournamentAddress = await tournament.getAddress();
  console.log("Tournament deployed to:", tournamentAddress);

  console.log("\n--- Deployment Summary ---");
  console.log("GameArena:  ", arenaAddress);
  console.log("Tournament: ", tournamentAddress);
  console.log("\nUpdate your .env file:");
  console.log(`GAME_ARENA_ADDRESS=${arenaAddress}`);
  console.log(`TOURNAMENT_ADDRESS=${tournamentAddress}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
