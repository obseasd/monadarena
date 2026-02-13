require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../.env" });

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x" + "0".repeat(64);

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      evmVersion: "paris",
    },
  },
  networks: {
    monadTestnet: {
      url: "https://testnet-rpc.monad.xyz",
      chainId: 10143,
      accounts: [PRIVATE_KEY],
      gasPrice: "auto",
    },
    monadMainnet: {
      url: "https://rpc.monad.xyz",
      chainId: 143,
      accounts: [PRIVATE_KEY],
      gasPrice: "auto",
    },
  },
  paths: {
    sources: "./src",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
