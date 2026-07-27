import json

from eth_utils import is_address, to_checksum_address
from web3 import Web3

from eth_rescue import templates
from eth_rescue import ui
from eth_rescue.abi import ERC721_OWNER_OF_ABI
from eth_rescue.prompts import (
    PromptCancelled,
    prompt_address,
    prompt_int,
    prompt_path,
    prompt_select,
    prompt_text,
)
from eth_rescue.templates import GAS_GENERIC
from eth_rescue.types import RescueData

REQUIRED_ACTION_KEYS = ("address", "function_signature", "args")
TRANSIENT_AUCTION_HOUSES = {
    to_checksum_address("0x6f66b95a0c512f3497fb46660e0bc3b94b989f8d"),
}


def _validate_actions(data: object) -> list[RescueData]:
    """Validate raw JSON into a list of rescue actions, raising on bad shapes."""
    if not isinstance(data, list) or not data:
        raise ValueError("config must be a non-empty JSON list of actions")
    for i, action in enumerate(data, 1):
        if not isinstance(action, dict):
            raise ValueError(f"action #{i} must be a JSON object")
        missing = [key for key in REQUIRED_ACTION_KEYS if key not in action]
        if missing:
            raise ValueError(f"action #{i} is missing keys: {', '.join(missing)}")
        if not isinstance(action["args"], list):
            raise ValueError(f"action #{i} 'args' must be a JSON array")
        if not is_address(action["address"]):
            raise ValueError(f"action #{i} has an invalid contract address")
        signature = action["function_signature"]
        if (
            not isinstance(signature, str)
            or "(" not in signature
            or not signature.endswith(")")
        ):
            raise ValueError(f"action #{i} has an invalid function signature")
        gas_estimate = action.get("gas_estimate", GAS_GENERIC)
        if (
            isinstance(gas_estimate, bool)
            or not isinstance(gas_estimate, int)
            or gas_estimate <= 0
        ):
            raise ValueError(
                f"action #{i} 'gas_estimate' (gas limit) must be a positive integer"
            )
        action["address"] = to_checksum_address(action["address"])
        action["gas_estimate"] = gas_estimate
    return data


def _load_config() -> list[RescueData]:
    """Power-user path: load an existing JSON config of rescue actions."""
    while True:
        path = prompt_path("Path to JSON config file")
        try:
            with open(path) as f:
                actions = _validate_actions(json.load(f))
            ui.success(f"Loaded {len(actions)} action(s) from {path}")
            return actions
        except (OSError, ValueError, json.JSONDecodeError) as e:
            ui.warning(f"Could not load config: {e}")


def _build_actions(
    w3: Web3, safe_wallet: str, victim_hint: str
) -> list[RescueData] | None:
    """Ask the user which kind of rescue and gather its ordered actions."""
    ui.info("While adding an action, type cancel, back, or exit to abandon it.")
    choice = prompt_select(
        "What do you want to rescue?",
        [
            ("ERC721 NFT", "erc721"),
            ("Transient Auction House ERC721", "transient_erc721"),
            ("ERC1155 NFT", "erc1155"),
            ("ERC20 token", "erc20"),
            ("Contract ownership", "ownership"),
            ("Custom (advanced: function signature + args)", "custom"),
            ("Cancel current action", "cancel"),
        ],
    )

    if choice == "cancel":
        ui.warning("Cancelled current action.")
        return None

    try:
        if choice == "erc721":
            contract = prompt_address("NFT contract address", allow_cancel=True)
            token_id = prompt_int("Token ID", allow_cancel=True)
            return [
                templates.erc721_transfer(contract, victim_hint, safe_wallet, token_id)
            ]

        if choice == "transient_erc721":
            contract = prompt_address("NFT contract address", allow_cancel=True)
            token_id = prompt_int("Token ID", allow_cancel=True)
            try:
                owner = (
                    w3.eth.contract(address=contract, abi=ERC721_OWNER_OF_ABI)
                    .functions.ownerOf(token_id)
                    .call()
                )
                auction_house = to_checksum_address(owner)
            except Exception as e:
                ui.warning(f"Could not look up the current token owner: {e}")
                return None
            if auction_house not in TRANSIENT_AUCTION_HOUSES:
                ui.warning(
                    f"Current token owner {auction_house} is not a recognized "
                    "Transient Auction House."
                )
                return None
            return templates.transient_auction_house_erc721_rescue(
                auction_house, contract, victim_hint, safe_wallet, token_id
            )

        if choice == "erc1155":
            contract = prompt_address("NFT contract address", allow_cancel=True)
            token_id = prompt_int("Token ID", allow_cancel=True)
            amount = prompt_int("Amount to transfer", allow_cancel=True)
            return [
                templates.erc1155_transfer(
                    contract, victim_hint, safe_wallet, token_id, amount
                )
            ]

        if choice == "erc20":
            contract = prompt_address("Token contract address", allow_cancel=True)
            ui.info(
                "Amount is in base units / wei. Example: 1 token with 18 decimals "
                "is 1000000000000000000."
            )
            amount = prompt_int("Amount to transfer (base units)", allow_cancel=True)
            return [templates.erc20_transfer(contract, safe_wallet, amount)]

        if choice == "ownership":
            contract = prompt_address(
                "Contract address to transfer ownership of",
                allow_cancel=True,
            )
            return [templates.transfer_ownership(contract, safe_wallet)]

        contract = prompt_address("Target contract address", allow_cancel=True)
        sig = prompt_text(
            "Function signature",
            default="transfer(address,uint256)",
            allow_cancel=True,
        )
        while True:
            raw_args = prompt_text(
                'Args as JSON array (e.g. ["0xabc...", 78])',
                default="[]",
                allow_cancel=True,
            )
            try:
                args = json.loads(raw_args) if raw_args else []
                if not isinstance(args, list):
                    raise ValueError("args must be a JSON array")
                break
            except (ValueError, json.JSONDecodeError) as e:
                ui.warning(f"Could not parse args: {e}")
        return [templates.custom(contract, sig, args)]
    except PromptCancelled:
        ui.warning("Cancelled current action.")
        return None


def print_plan(actions: list[RescueData]) -> None:
    """Render the list of rescue actions in plain English."""
    ui.render_rescue_plan(actions)


def revise_rescue_data(
    w3: Web3,
    actions: list[RescueData],
    safe_wallet: str,
    victim_address: str,
    failing_action_index: int | None = None,
) -> list[RescueData] | None:
    """Interactively revise a plan after simulation failure."""
    revised = list(actions)
    while True:
        choices = []
        if failing_action_index is not None and failing_action_index < len(revised):
            choices.append(
                (f"Remove failing action #{failing_action_index + 1}", "remove")
            )
        choices.extend(
            [
                ("Add another action", "add"),
                ("Rebuild the entire plan", "rebuild"),
                ("Use this revised plan", "finish"),
                ("Cancel without sending", "cancel"),
            ]
        )
        choice = prompt_select("How do you want to correct the rescue plan?", choices)
        if choice == "remove":
            revised.pop(failing_action_index)
            failing_action_index = None
            print_plan(revised)
        elif choice == "add":
            new_actions = _build_actions(w3, safe_wallet, victim_address)
            if new_actions is not None:
                revised.extend(new_actions)
                print_plan(revised)
        elif choice == "rebuild":
            return build_rescue_data(w3, victim_address, safe_wallet)
        elif choice == "finish":
            if revised:
                return revised
            ui.warning("A rescue plan must contain at least one action.")
        else:
            return None


def build_rescue_data(
    w3: Web3,
    victim_address: str = "",
    safe_wallet: str | None = None,
) -> list[RescueData]:
    """
    Step 1 of the flow: produce the list of rescue actions, either by loading a
    JSON config or by walking the guided wizard.
    """
    setup_mode = prompt_select(
        "How would you like to set up the rescue?",
        [
            ("Guided wizard (recommended)", "wizard"),
            ("Load a saved JSON config file", "config"),
        ],
    )
    if setup_mode == "config":
        return _load_config()

    victim_hint = victim_address or prompt_address(
        "Compromised (victim) wallet address"
    )
    if safe_wallet is None:
        safe_wallet = prompt_address("Safe wallet to send everything to")

    actions: list[RescueData] = []
    while True:
        if actions:
            next_step = prompt_select(
                "What next?",
                [
                    ("Add another action", "add"),
                    ("Review current plan", "review"),
                    ("Finish this plan", "finish"),
                ],
            )
            if next_step == "review":
                print_plan(actions)
                continue
            if next_step == "finish":
                break

        new_actions = _build_actions(w3, safe_wallet, victim_hint)
        if new_actions is not None:
            actions.extend(new_actions)

    print_plan(actions)
    return actions
