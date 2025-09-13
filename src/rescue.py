import os
import json
from getpass import getpass
from dotenv import load_dotenv
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound

from src.flashbots import flashbot, FlashbotsWeb3
from src.foundry import build_calldata
from src.types import RescueData

load_dotenv()


def rescue(config_fp: str, extra_priority_fee: int):
    # get auth account keystore password
    auth_account_pw = getpass("Enter auth account keystore password: ")

    # get auth keystore json
    with open(os.environ.get("AUTH_ACCOUNT_KEYSTORE_FILE"), "r") as auth_keystore:
        auth_account_json = json.load(auth_keystore)

    # get the auth account pk
    auth_account_pk = Account.decrypt(auth_account_json, auth_account_pw)

    # get gas account keystore password
    gas_account_pw = getpass("Enter gas account keystore password: ")

    # get gas keystore json
    with open(os.environ.get("GAS_ACCOUNT_KEYSTORE_FILE"), "r") as gas_keystore:
        gas_account_json = json.load(gas_keystore)

    # get the gas account pk
    gas_account_pk = Account.decrypt(gas_account_json, gas_account_pw)

    # setup
    victim_account: LocalAccount = Account.from_key(os.environ.get("VICTIM_ACCOUNT_PK"))
    gas_account: LocalAccount = Account.from_key(gas_account_pk)
    auth_account: LocalAccount = Account.from_key(auth_account_pk)
    w3: FlashbotsWeb3 = Web3(HTTPProvider("https://ethereum-rpc.publicnode.com"))
    flashbot(w3, auth_account, os.environ.get("RELAY_URL"))

    print(f"Victim Address: {victim_account.address}")
    print(f"Gas Address: {gas_account.address}")

    # get gas data
    latest_block = w3.eth.get_block("latest")
    base_fee = int(latest_block["baseFeePerGas"] * 1.25)
    priority_fee = w3.eth.max_priority_fee + w3.to_wei(extra_priority_fee, "gwei")
    max_fee_per_gas = 2 * base_fee + priority_fee

    print(f"Base Gas Fee: {w3.from_wei(base_fee, 'gwei')} gwei")
    print(f"Priority Fee: {w3.from_wei(priority_fee, 'gwei')} gwei")

    # build rescue txs
    with open(config_fp, "r") as f:
        rescue_data: list[RescueData] = json.load(f)
        if not isinstance(rescue_data, list):
            raise Exception("Invalid rescue data type")

    rescue_txs = []
    total_rescue_cost = 0
    victim_nonce = w3.eth.get_transaction_count(victim_account.address)
    for i, data in enumerate(rescue_data):
        tx_data = build_calldata(data["function_signature"], data["args"])
        rescue_tx = {
            "to": data["address"],
            "data": tx_data,
            "gas": data["gas_estimate"],
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": priority_fee,
            "nonce": victim_nonce + i,
            "chainId": w3.eth.chain_id,
        }
        rescue_txs.append(rescue_tx)
        total_rescue_cost += int(data["gas_estimate"] * max_fee_per_gas)
    print(f"Total Rescue Cost: {w3.from_wei(total_rescue_cost, 'ether')} ETH")

    # build transaction to fund owner wallet from the sender wallet
    funding_tx = {
        "to": victim_account.address,
        "value": total_rescue_cost,
        "gas": 21000,
        "maxFeePerGas": max_fee_per_gas,
        "maxPriorityFeePerGas": priority_fee,
        "nonce": w3.eth.get_transaction_count(gas_account.address),
        "chainId": w3.eth.chain_id,
    }

    # sign txs and build bundle
    signed_funding_tx = w3.eth.account.sign_transaction(
        funding_tx, private_key=gas_account.key
    )
    signed_rescue_txs = [
        w3.eth.account.sign_transaction(tx, private_key=victim_account.key)
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
        print(f"🫆 Transaction Hashes: {[r.transactionHash.hex() for r in receipts]}")
    except TransactionNotFound:
        print("❌ Bundle not found in any of the blocks. Try again.")
