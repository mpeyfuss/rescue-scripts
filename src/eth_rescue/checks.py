from dataclasses import dataclass
from typing import Literal

from eth_utils import to_checksum_address
from web3 import Web3

from eth_rescue.abi import (
    ERC20_BALANCE_OF_ABI,
    ERC721_OWNER_OF_ABI,
    ERC1155_BALANCE_OF_ABI,
    OWNABLE_OWNER_ABI,
)
from eth_rescue.types import ActionOutcome, RescueData

CheckKind = Literal["erc20", "erc721", "erc1155", "ownership"]


@dataclass(frozen=True)
class Check:
    kind: CheckKind
    contract: str
    recipient: str
    token_id: int | None = None
    amount: int | None = None


def infer_check(data: RescueData) -> Check | None:
    """Derive a recipient-side postcondition from a known function signature.

    Checks are recipient-side deliberately: victim-side deltas would
    misclassify an attacker draining the asset mid-race as a successful rescue.
    """
    contract = to_checksum_address(data["address"])
    args = data["args"]
    match data["function_signature"]:
        case "transfer(address,uint256)":
            return Check(
                "erc20",
                contract,
                to_checksum_address(args[0]),
                amount=int(args[1]),
            )
        case "transferFrom(address,address,uint256)":
            return Check(
                "erc721",
                contract,
                to_checksum_address(args[1]),
                token_id=int(args[2]),
            )
        case "safeTransferFrom(address,address,uint256,uint256,bytes)":
            return Check(
                "erc1155",
                contract,
                to_checksum_address(args[1]),
                token_id=int(args[2]),
                amount=int(args[3]),
            )
        case "transferOwnership(address)":
            return Check("ownership", contract, to_checksum_address(args[0]))
        case _:
            return None


def infer_checks(rescue_data: list[RescueData]) -> dict[int, Check]:
    checks: dict[int, Check] = {}
    for index, data in enumerate(rescue_data):
        check = infer_check(data)
        if check is not None:
            checks[index] = check
    return checks


def _recipient_balance(w3: Web3, check: Check) -> int:
    if check.kind == "erc20":
        contract = w3.eth.contract(address=check.contract, abi=ERC20_BALANCE_OF_ABI)
        return contract.functions.balanceOf(check.recipient).call()
    contract = w3.eth.contract(address=check.contract, abi=ERC1155_BALANCE_OF_ABI)
    return contract.functions.balanceOf(check.recipient, check.token_id).call()


def snapshot_checks(w3: Web3, checks: dict[int, Check]) -> dict[int, int]:
    """Record recipient balances before the rescue for delta-based checks."""
    snapshot: dict[int, int] = {}
    for index, check in checks.items():
        if check.kind in ("erc20", "erc1155"):
            snapshot[index] = _recipient_balance(w3, check)
    return snapshot


def _check_passed(w3: Web3, check: Check, snapshot_balance: int | None) -> bool:
    try:
        match check.kind:
            case "erc20" | "erc1155":
                received = _recipient_balance(w3, check) - (snapshot_balance or 0)
                return received >= (check.amount or 0)
            case "erc721":
                contract = w3.eth.contract(
                    address=check.contract, abi=ERC721_OWNER_OF_ABI
                )
                owner = contract.functions.ownerOf(check.token_id).call()
            case "ownership":
                contract = w3.eth.contract(
                    address=check.contract, abi=OWNABLE_OWNER_ABI
                )
                owner = contract.functions.owner().call()
        return to_checksum_address(owner) == check.recipient
    except Exception:
        return False


def evaluate_checks(
    w3: Web3,
    checks: dict[int, Check],
    snapshot: dict[int, int],
    action_count: int,
) -> list[ActionOutcome]:
    outcomes: list[ActionOutcome] = []
    for index in range(action_count):
        check = checks.get(index)
        if check is None:
            outcomes.append(ActionOutcome(index, "unverified"))
        elif _check_passed(w3, check, snapshot.get(index)):
            outcomes.append(ActionOutcome(index, "rescued"))
        else:
            outcomes.append(ActionOutcome(index, "failed"))
    return outcomes
