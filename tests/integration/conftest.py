import json
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import HTTPProvider, Web3
from web3.types import TxReceipt

from eth_rescue.types import BundleEntry, SimulationResult

ANVIL_HARDFORK = os.environ.get("ANVIL_HARDFORK", "osaka")
CONTRACT_OUT = Path(__file__).parent / "contracts" / "out" / "Fixtures.sol"


def _available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def anvil_w3() -> Iterator[Web3]:
    if os.environ.get("RUN_ANVIL_INTEGRATION") != "1":
        pytest.skip("set RUN_ANVIL_INTEGRATION=1 to run Anvil tests")
    executable = shutil.which("anvil")
    if executable is None:
        pytest.skip("anvil is not installed")

    port = _available_port()
    process = subprocess.Popen(
        [
            executable,
            "--hardfork",
            ANVIL_HARDFORK,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--chain-id",
            "31337",
            "--quiet",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    w3 = Web3(HTTPProvider(url, request_kwargs={"timeout": 10}))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate()
            pytest.fail(
                f"Anvil exited with code {process.returncode} while starting with "
                f"{ANVIL_HARDFORK}:\n{output}"
            )
        if w3.is_connected():
            break
        time.sleep(0.05)
    else:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
        pytest.fail(
            f"Anvil did not start within 10 seconds using {ANVIL_HARDFORK}:\n" + output
        )

    try:
        yield w3
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@dataclass(frozen=True)
class SequentialSubmission:
    transaction_receipts: tuple[TxReceipt, ...]

    def wait(self) -> None:
        return None

    def receipts(self) -> list[TxReceipt]:
        return list(self.transaction_receipts)


class SequentialRelay:
    """Anvil relay double; sequential execution does not model bundle atomicity."""

    def __init__(self, w3: Web3):
        self.w3 = w3
        self.simulated: list[list[BundleEntry]] = []
        self.sent: list[list[BundleEntry]] = []
        self.submitted_receipts: list[list[TxReceipt]] = []

    def _execute(
        self, bundle: list[BundleEntry]
    ) -> tuple[list[dict[str, Any]], list[TxReceipt]]:
        results: list[dict[str, Any]] = []
        receipts: list[TxReceipt] = []
        for entry in bundle:
            try:
                tx_hash = self.w3.eth.send_raw_transaction(entry["signed_transaction"])
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                receipts.append(receipt)
                result: dict[str, Any] = {
                    "txHash": tx_hash.hex(),
                    "gasUsed": receipt["gasUsed"],
                }
                if receipt["status"] != 1:
                    result["revert"] = "transaction reverted"
                results.append(result)
            except Exception as error:
                results.append({"error": str(error)})
        return results, receipts

    def simulate(
        self, bundle: list[BundleEntry], block_tag: int | str | None = None
    ) -> SimulationResult:
        del block_tag
        self.simulated.append(bundle)
        snapshot = self.w3.provider.make_request("evm_snapshot", [])["result"]
        try:
            results, _ = self._execute(bundle)
            return {
                "bundleHash": "0xsequential-simulation",
                "results": results,
                "totalGasUsed": sum(result.get("gasUsed", 0) for result in results),
            }
        finally:
            reverted = self.w3.provider.make_request("evm_revert", [snapshot])["result"]
            if not reverted:
                raise RuntimeError("Anvil failed to revert relay simulation snapshot")

    def send_bundle(
        self, bundle: list[BundleEntry], target_block_number: int
    ) -> SequentialSubmission:
        del target_block_number
        self.sent.append(bundle)
        _results, receipts = self._execute(bundle)
        self.submitted_receipts.append(receipts)
        return SequentialSubmission(tuple(receipts))


def _artifact(name: str) -> tuple[list[dict[str, Any]], str]:
    path = CONTRACT_OUT / f"{name}.json"
    if not path.exists():
        pytest.fail("integration contracts are not compiled; run make test-integration")
    artifact = json.loads(path.read_text())
    return artifact["abi"], artifact["bytecode"]["object"]


def _deploy(w3: Web3, name: str):
    abi, bytecode = _artifact(name)
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = factory.constructor().transact({"from": w3.eth.accounts[0]})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1
    return w3.eth.contract(address=receipt["contractAddress"], abi=abi)


@pytest.fixture
def rescue_accounts(anvil_w3: Web3) -> tuple[LocalAccount, LocalAccount, LocalAccount]:
    victim = Account.create()
    gas = Account.create()
    safe = Account.create()
    funder = anvil_w3.eth.accounts[0]
    for address, amount in (
        (victim.address, anvil_w3.to_wei(1, "ether")),
        (gas.address, anvil_w3.to_wei(10, "ether")),
    ):
        tx_hash = anvil_w3.eth.send_transaction(
            {"from": funder, "to": address, "value": amount}
        )
        anvil_w3.eth.wait_for_transaction_receipt(tx_hash)
    return victim, gas, safe


@pytest.fixture
def sequential_relay(anvil_w3: Web3) -> SequentialRelay:
    relay = SequentialRelay(anvil_w3)
    anvil_w3.relay = relay
    return relay


@pytest.fixture
def code_rejecting_erc20(anvil_w3: Web3, rescue_accounts):
    victim, _gas, _safe = rescue_accounts
    token = _deploy(anvil_w3, "FixtureCodeRejectingERC20")
    receipt = anvil_w3.eth.wait_for_transaction_receipt(
        token.functions.mint(victim.address, 500).transact(
            {"from": anvil_w3.eth.accounts[0]}
        )
    )
    assert receipt["status"] == 1
    return token


@pytest.fixture
def false_returning_erc20(anvil_w3: Web3, rescue_accounts):
    victim, _gas, _safe = rescue_accounts
    token = _deploy(anvil_w3, "FixtureFalseReturningERC20")
    receipt = anvil_w3.eth.wait_for_transaction_receipt(
        token.functions.mint(victim.address, 500).transact(
            {"from": anvil_w3.eth.accounts[0]}
        )
    )
    assert receipt["status"] == 1
    return token


@pytest.fixture
def asset_contracts(anvil_w3: Web3, rescue_accounts):
    victim, _gas, _safe = rescue_accounts
    contracts = {
        "erc20": _deploy(anvil_w3, "FixtureERC20"),
        "erc721": _deploy(anvil_w3, "FixtureERC721"),
        "erc1155": _deploy(anvil_w3, "FixtureERC1155"),
        "ownable": _deploy(anvil_w3, "FixtureOwnable"),
        "auction": _deploy(anvil_w3, "FixtureAuctionHouse"),
        "delegate": _deploy(anvil_w3, "FixtureDelegateTarget"),
    }
    funder = anvil_w3.eth.accounts[0]
    setup = (
        contracts["erc20"].functions.mint(victim.address, 1_000),
        contracts["erc721"].functions.mint(victim.address, 1),
        contracts["erc1155"].functions.mint(victim.address, 7, 25),
        contracts["ownable"].functions.transferOwnership(victim.address),
    )
    for call in setup:
        receipt = anvil_w3.eth.wait_for_transaction_receipt(
            call.transact({"from": funder})
        )
        assert receipt["status"] == 1
    return contracts
