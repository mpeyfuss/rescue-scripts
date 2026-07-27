import json
from pathlib import Path

import pytest
from eth_utils import to_canonical_address

from eth_rescue import checks, contract, rescue, templates

pytestmark = pytest.mark.integration

DELEGATION_PREFIX = bytes.fromhex("ef0100")
ETH_RESCUE_ARTIFACT = (
    Path(__file__).parents[2] / "contracts" / "out" / "EthRescue.sol" / "EthRescue.json"
)


def _execute_7702(w3, victim, gas, safe, rescue_data):
    prepared = rescue.prepare_actions(rescue_data)
    bundle = rescue.prepare_7702_bundle(w3, victim, gas, prepared, safe.address, 0.0)
    simulation = rescue.simulate_prepared_bundle(w3, bundle)
    assert simulation.ok
    assert rescue.send_with_retry(
        w3, victim, gas, prepared, safe.address, 0.0, rescue.prepare_7702_bundle
    )
    return bundle


def _execute_legacy(w3, victim, gas, safe, rescue_data):
    prepared = rescue.prepare_actions(rescue_data)
    bundle = rescue.prepare_bundle(w3, victim, gas, prepared, safe.address, 0.0)
    simulation = rescue.simulate_prepared_bundle(w3, bundle)
    assert simulation.ok
    assert rescue.send_with_retry(w3, victim, gas, prepared, safe.address, 0.0)
    return bundle


def test_bytecode_constant_matches_forge_build():
    if not ETH_RESCUE_ARTIFACT.exists():
        pytest.skip("run `forge build --root contracts` (make test-integration)")
    artifact = json.loads(ETH_RESCUE_ARTIFACT.read_text())
    built = bytes.fromhex(artifact["bytecode"]["object"].removeprefix("0x"))
    assert contract.ETH_RESCUE_CREATION_BYTECODE == built, (
        "Embedded EthRescue bytecode is stale; regenerate src/eth_rescue/contract.py"
    )


def test_pure_7702_rescues_asset_matrix_and_sweeps_all_eth(
    anvil_w3, rescue_accounts, asset_contracts, sequential_relay
):
    victim, gas, safe = rescue_accounts
    erc20 = asset_contracts["erc20"]
    erc721 = asset_contracts["erc721"]
    erc1155 = asset_contracts["erc1155"]
    ownable = asset_contracts["ownable"]
    gas_nonce = anvil_w3.eth.get_transaction_count(gas.address)

    rescue_data = [
        templates.erc20_transfer(erc20.address, safe.address, 1_000),
        templates.erc721_transfer(erc721.address, victim.address, safe.address, 1),
        templates.erc1155_transfer(
            erc1155.address, victim.address, safe.address, 7, 25
        ),
        templates.transfer_ownership(ownable.address, safe.address),
    ]
    check_map = checks.infer_checks(rescue_data)
    snapshot = checks.snapshot_checks(anvil_w3, check_map)

    bundle = _execute_7702(anvil_w3, victim, gas, safe, rescue_data)

    assert [t.role for t in bundle.transactions] == ["deploy", "rescue-7702"]
    assert erc20.functions.balanceOf(safe.address).call() == 1_000
    assert erc721.functions.ownerOf(1).call() == safe.address
    assert erc1155.functions.balanceOf(safe.address, 7).call() == 25
    assert ownable.functions.owner().call() == safe.address

    # entire victim balance swept to safe; victim left with nothing
    assert anvil_w3.eth.get_balance(victim.address) == 0
    assert anvil_w3.eth.get_balance(safe.address) == anvil_w3.to_wei(1, "ether")

    # victim is delegated to the contract deployed at the precomputed address
    expected_code = DELEGATION_PREFIX + to_canonical_address(bundle.rescue_contract)
    assert bytes(anvil_w3.eth.get_code(victim.address)) == expected_code
    assert anvil_w3.eth.get_transaction_count(gas.address) == gas_nonce + 2

    outcomes = checks.evaluate_checks(anvil_w3, check_map, snapshot, len(rescue_data))
    assert all(o.status == "rescued" for o in outcomes)


def test_state_checks_flag_failed_transfers(
    anvil_w3,
    rescue_accounts,
    asset_contracts,
    code_rejecting_erc20,
    false_returning_erc20,
    sequential_relay,
):
    victim, gas, safe = rescue_accounts
    erc20 = asset_contracts["erc20"]

    rescue_data = [
        templates.erc20_transfer(erc20.address, safe.address, 1_000),
        templates.erc20_transfer(code_rejecting_erc20.address, safe.address, 500),
        templates.erc20_transfer(false_returning_erc20.address, safe.address, 500),
    ]
    check_map = checks.infer_checks(rescue_data)
    snapshot = checks.snapshot_checks(anvil_w3, check_map)

    _execute_7702(anvil_w3, victim, gas, safe, rescue_data)

    outcomes = checks.evaluate_checks(anvil_w3, check_map, snapshot, len(rescue_data))
    assert [o.status for o in outcomes] == ["rescued", "failed", "failed"]
    # the good token still moved despite the two failures in the same call
    assert erc20.functions.balanceOf(safe.address).call() == 1_000
    assert code_rejecting_erc20.functions.balanceOf(safe.address).call() == 0
    assert false_returning_erc20.functions.balanceOf(safe.address).call() == 0


def test_two_phase_legacy_fallback_recovers_code_rejecting_token(
    anvil_w3, rescue_accounts, code_rejecting_erc20, sequential_relay
):
    victim, gas, safe = rescue_accounts

    rescue_data = [
        templates.erc20_transfer(code_rejecting_erc20.address, safe.address, 500)
    ]
    check_map = checks.infer_checks(rescue_data)
    snapshot = checks.snapshot_checks(anvil_w3, check_map)

    _execute_7702(anvil_w3, victim, gas, safe, rescue_data)

    outcomes = checks.evaluate_checks(anvil_w3, check_map, snapshot, len(rescue_data))
    assert outcomes[0].status == "failed"
    assert rescue._has_7702_delegation(anvil_w3, victim.address)

    # Phase 2: legacy fallback undelegates then transfers directly from the victim.
    bundle = _execute_legacy(anvil_w3, victim, gas, safe, rescue_data)

    assert [t.role for t in bundle.transactions] == [
        "undelegate",
        "fund",
        "rescue",
        "sweep",
    ]
    assert bytes(anvil_w3.eth.get_code(victim.address)) == b""
    assert code_rejecting_erc20.functions.balanceOf(safe.address).call() == 500
