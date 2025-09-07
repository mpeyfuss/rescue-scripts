import os
from dotenv import load_dotenv
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
from src.flashbots import flashbot, FlashbotsWeb3
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound
from web3.contract.contract import Contract

load_dotenv()

##################################
# Edit these values
##################################
CONTRACTS = [
    "0xEF561A49Cc31938661D02b5357088c2b153E486e",
    "0xF1D3624780EC22208C84A43FB3457eba32123EC6",
]
NEW_OWNER_ADDRESS = "0x74A7b842FDeb244C152aa5BC8B7fbae362091EE1"
GAS_ESTIMATE = 40_000
EXTRA_PRIORITY_FEE_GWEI = 0
RELAY_URL = "https://relay.flashbots.net"


##################################
# Rescue Script
##################################
def rescue():
    # setup
    owner_account: LocalAccount = Account.from_key(os.environ.get("OWNER_ACCOUNT_PK"))
    sender_account: LocalAccount = Account.from_key(os.environ.get("SENDER_ACCOUNT_PK"))
    auth_account: LocalAccount = Account.from_key(os.environ.get("AUTH_ACCOUNT_PK"))
    w3: FlashbotsWeb3 = Web3(HTTPProvider("https://ethereum-rpc.publicnode.com"))
    flashbot(w3, auth_account, RELAY_URL)

    print(f"Owner Address: {owner_account.address}")
    print(f"Sender Address: {sender_account.address}")

    while True:
        # get gas data
        latest_block = w3.eth.get_block("latest")
        base_fee = int(latest_block["baseFeePerGas"] * 1.25)
        priority_fee = w3.eth.max_priority_fee + w3.to_wei(
            EXTRA_PRIORITY_FEE_GWEI, "gwei"
        )
        max_fee_per_gas = 2 * base_fee + priority_fee

        print(f"Base Gas Fee: {w3.from_wei(base_fee, 'gwei')} gwei")
        print(f"Priority Fee: {w3.from_wei(priority_fee, 'gwei')} gwei")

        # build rescue txs
        rescue_txs = []
        total_rescue_cost = 0
        owner_nonce = w3.eth.get_transaction_count(owner_account.address)
        for i, contract_address in enumerate(CONTRACTS):
            MINIMAL_OWNABLE_ABI = [
                {
                    "inputs": [
                        {
                            "internalType": "address",
                            "name": "newOwner",
                            "type": "address",
                        }
                    ],
                    "name": "transferOwnership",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function",
                },
            ]
            contract: Contract = w3.eth.contract(
                address=contract_address, abi=MINIMAL_OWNABLE_ABI
            )
            tx_data = contract.encode_abi(
                "transferOwnership", [Web3.to_checksum_address(NEW_OWNER_ADDRESS)]
            )
            rescue_tx = {
                "to": contract_address,
                "data": tx_data,
                "gas": GAS_ESTIMATE,
                "maxFeePerGas": max_fee_per_gas,
                "maxPriorityFeePerGas": priority_fee,
                "nonce": owner_nonce + i,
                "chainId": w3.eth.chain_id,
            }
            rescue_txs.append(rescue_tx)
            total_rescue_cost += int(GAS_ESTIMATE * max_fee_per_gas * 1.05)
        print(f"Total Rescue Cost: {w3.from_wei(total_rescue_cost, 'ether')} ETH")

        # build transaction to fund owner wallet from the sender wallet
        funding_tx = {
            "to": owner_account.address,
            "value": total_rescue_cost,
            "gas": 21000,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": priority_fee,
            "nonce": w3.eth.get_transaction_count(sender_account.address),
            "chainId": w3.eth.chain_id,
        }

        # sign txs and build bundle
        signed_funding_tx = w3.eth.account.sign_transaction(
            funding_tx, private_key=sender_account.key
        )
        signed_rescue_txs = [
            w3.eth.account.sign_transaction(tx, private_key=owner_account.key)
            for tx in rescue_txs
        ]
        bundle = [
            {"signed_transaction": signed_funding_tx.rawTransaction},
            *[{"signed_transaction": tx.rawTransaction} for tx in signed_rescue_txs],
        ]

        # send bundle
        block = w3.eth.block_number
        target_block = block + 1

        send_result = w3.flashbots.send_bundle(
            bundle,
            target_block_number=target_block,
        )
        print("Bundle sent, waiting for confirmations...")

        send_result.wait()
        try:
            receipts = send_result.receipts()
            print("🚀 Bundle Included!")
            print(f"🔗 Block: {receipts[0].blockNumber}")
            print(
                f"🫆 Transaction Hashes: {[r.transactionHash.hex() for r in receipts]}"
            )
            break
        except TransactionNotFound:
            print("❌ Bundle not found in any of the blocks. Try again.")
