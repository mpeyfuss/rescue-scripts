import pytest
from eth_account import Account
from web3 import Web3

from eth_rescue import rescue, templates

pytestmark = pytest.mark.integration


def _send_account_transaction(w3, account, transaction):
    signed = account.sign_transaction(transaction)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


def _execute_rescue(w3, victim, gas, safe, rescue_data):
    prepared = rescue.prepare_actions(rescue_data)
    preview_bundle = rescue.prepare_bundle(w3, victim, gas, prepared, safe.address, 0.0)
    simulation = rescue.simulate_prepared_bundle(w3, preview_bundle)
    assert simulation.ok
    assert rescue.send_with_retry(w3, victim, gas, prepared, safe.address, 0.0)
    return preview_bundle


def _delegate_victim(w3: Web3, victim, gas, target: str) -> None:
    priority_fee, max_fee_per_gas = rescue._compute_fees(w3, 0.0)
    authorization = Account.sign_authorization(
        {"chainId": w3.eth.chain_id, "address": target, "nonce": 0}, victim.key
    )
    signed = gas.sign_transaction(
        {
            "type": rescue.SET_CODE_TX_TYPE,
            "chainId": w3.eth.chain_id,
            "nonce": w3.eth.get_transaction_count(gas.address),
            "maxPriorityFeePerGas": priority_fee,
            "maxFeePerGas": max_fee_per_gas,
            "gas": rescue.UNDELEGATE_TX_GAS,
            "to": gas.address,
            "value": 0,
            "data": b"",
            "accessList": [],
            "authorizationList": [authorization],
        }
    )
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1


def test_plain_victim_rescues_asset_matrix_and_sweeps_eth(
    anvil_w3, rescue_accounts, asset_contracts, sequential_relay
):
    victim, gas, safe = rescue_accounts
    erc20 = asset_contracts["erc20"]
    erc721 = asset_contracts["erc721"]
    erc1155 = asset_contracts["erc1155"]
    ownable = asset_contracts["ownable"]
    victim_nonce = anvil_w3.eth.get_transaction_count(victim.address)
    gas_nonce = anvil_w3.eth.get_transaction_count(gas.address)
    gas_balance = anvil_w3.eth.get_balance(gas.address)

    bundle = _execute_rescue(
        anvil_w3,
        victim,
        gas,
        safe,
        [
            templates.erc20_transfer(erc20.address, safe.address, 1_000),
            templates.erc721_transfer(erc721.address, victim.address, safe.address, 1),
            templates.erc1155_transfer(
                erc1155.address, victim.address, safe.address, 7, 25
            ),
            templates.transfer_ownership(ownable.address, safe.address),
        ],
    )

    assert [transaction.role for transaction in bundle.transactions] == [
        "fund",
        "rescue",
        "rescue",
        "rescue",
        "rescue",
        "sweep",
    ]
    assert erc20.functions.balanceOf(safe.address).call() == 1_000
    assert erc721.functions.ownerOf(1).call() == safe.address
    assert erc1155.functions.balanceOf(safe.address, 7).call() == 25
    assert ownable.functions.owner().call() == safe.address
    assert anvil_w3.eth.get_balance(safe.address) == bundle.sweep_value
    assert anvil_w3.eth.get_transaction_count(victim.address) == victim_nonce + 5
    assert anvil_w3.eth.get_transaction_count(gas.address) == gas_nonce + 1
    assert 0 <= anvil_w3.eth.get_balance(victim.address) < bundle.victim_funding
    assert (
        0
        < gas_balance - anvil_w3.eth.get_balance(gas.address)
        < bundle.required_funding
    )
    assert len(sequential_relay.sent) == rescue.BUNDLE_BLOCK_RANGE
    assert len(sequential_relay.submitted_receipts[0]) == len(bundle.transactions)
    assert all(
        receipt["status"] == 1 for receipt in sequential_relay.submitted_receipts[0]
    )


def test_delegated_victim_is_undelegated_before_rescue(
    anvil_w3, rescue_accounts, asset_contracts, sequential_relay
):
    victim, gas, safe = rescue_accounts
    erc20 = asset_contracts["erc20"]
    _delegate_victim(anvil_w3, victim, gas, asset_contracts["delegate"].address)
    assert rescue._has_7702_delegation(anvil_w3, victim.address)
    starting_nonce = anvil_w3.eth.get_transaction_count(victim.address)

    bundle = _execute_rescue(
        anvil_w3,
        victim,
        gas,
        safe,
        [templates.erc20_transfer(erc20.address, safe.address, 1_000)],
    )

    assert [transaction.role for transaction in bundle.transactions] == [
        "undelegate",
        "fund",
        "rescue",
        "sweep",
    ]
    assert anvil_w3.eth.get_code(victim.address) == b""
    assert erc20.functions.balanceOf(safe.address).call() == 1_000
    assert anvil_w3.eth.get_transaction_count(victim.address) == starting_nonce + 3
    assert len(sequential_relay.sent) == rescue.BUNDLE_BLOCK_RANGE


def test_delist_then_transfer_rescues_escrowed_erc721(
    anvil_w3, rescue_accounts, asset_contracts, sequential_relay
):
    victim, gas, safe = rescue_accounts
    erc721 = asset_contracts["erc721"]
    auction = asset_contracts["auction"]
    approve = erc721.functions.approve(auction.address, 1).build_transaction(
        {
            "from": victim.address,
            "nonce": anvil_w3.eth.get_transaction_count(victim.address),
        }
    )
    assert _send_account_transaction(anvil_w3, victim, approve)["status"] == 1
    listing = auction.functions.list(erc721.address, 1).build_transaction(
        {
            "from": victim.address,
            "nonce": anvil_w3.eth.get_transaction_count(victim.address),
        }
    )
    assert _send_account_transaction(anvil_w3, victim, listing)["status"] == 1
    assert erc721.functions.ownerOf(1).call() == auction.address

    bundle = _execute_rescue(
        anvil_w3,
        victim,
        gas,
        safe,
        templates.transient_auction_house_erc721_rescue(
            auction.address, erc721.address, victim.address, safe.address, 1
        ),
    )

    assert [
        transaction.action_index
        for transaction in bundle.transactions
        if transaction.role == "rescue"
    ] == [0, 1]
    assert (
        auction.functions.seller(erc721.address, 1).call()
        == "0x0000000000000000000000000000000000000000"
    )
    assert erc721.functions.ownerOf(1).call() == safe.address
    assert len(sequential_relay.sent) == rescue.BUNDLE_BLOCK_RANGE


def test_reverting_action_rolls_back_simulation_and_blocks_submission(
    anvil_w3, rescue_accounts, asset_contracts, sequential_relay
):
    victim, gas, safe = rescue_accounts
    erc20 = asset_contracts["erc20"]
    prepared = rescue.prepare_actions(
        [templates.erc20_transfer(erc20.address, safe.address, 1_001)]
    )
    bundle = rescue.prepare_bundle(anvil_w3, victim, gas, prepared, safe.address, 0.0)
    before = {
        "victim_balance": anvil_w3.eth.get_balance(victim.address),
        "gas_balance": anvil_w3.eth.get_balance(gas.address),
        "victim_nonce": anvil_w3.eth.get_transaction_count(victim.address),
        "gas_nonce": anvil_w3.eth.get_transaction_count(gas.address),
        "token_balance": erc20.functions.balanceOf(victim.address).call(),
        "code": anvil_w3.eth.get_code(victim.address),
    }

    outcome = rescue.simulate_prepared_bundle(anvil_w3, bundle)

    assert not outcome.ok
    failure = outcome.failures[0]
    assert failure.role == "rescue"
    assert failure.action_index == 0
    assert before == {
        "victim_balance": anvil_w3.eth.get_balance(victim.address),
        "gas_balance": anvil_w3.eth.get_balance(gas.address),
        "victim_nonce": anvil_w3.eth.get_transaction_count(victim.address),
        "gas_nonce": anvil_w3.eth.get_transaction_count(gas.address),
        "token_balance": erc20.functions.balanceOf(victim.address).call(),
        "code": anvil_w3.eth.get_code(victim.address),
    }
    assert not rescue.send_with_retry(
        anvil_w3, victim, gas, prepared, safe.address, 0.0
    )
    assert sequential_relay.sent == []
