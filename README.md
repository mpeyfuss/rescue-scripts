# Whitehat Rescue Scripts
A compilation of whitehat rescue scripts for Ethereum.

## Background
When a private key or seedphrase is compromised, bad actors typically attach a sweeper bot to the account. So whenever any ETH is sent to the compromised wallet, the sweeper bot takes those funds before you can use the ETH for gas on any transactions to save NFTs, contract ownership, or any other onchain action.

These scripts use private bundled transactions through Flashbots to ensure that mulitple transactions are all included together in an atomic way and gets around sweeper bots.

## Getting Started
1. Create your .env file
2. Make sure you have [uv](https://docs.astral.sh/uv/) installed
3. Make sure you have [Foundry](https://getfoundry.sh/) installed
4. Create a config file (see `examples` for layout)
5. Run `make rescue`