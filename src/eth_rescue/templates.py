from eth_rescue.types import RescueData

# Fixed gas limits per action type, generously given
GAS_ERC20 = 75000
GAS_ERC721 = 150000
GAS_ERC1155 = 85000
GAS_OWNERSHIP = 40000
GAS_TRANSIENT_DELIST = 200000
GAS_GENERIC = 150000


def erc20_transfer(contract: str, to: str, amount: int) -> RescueData:
    """Transfer ERC20 tokens (amount in base units, e.g. wei) to a safe wallet."""
    return {
        "address": contract,
        "function_signature": "transfer(address,uint256)",
        "args": [to, amount],
        "gas_estimate": GAS_ERC20,
        "description": f"ERC20 transfer of {amount} (base units) to {to}",
    }


def erc721_transfer(
    contract: str, from_victim: str, to: str, token_id: int
) -> RescueData:
    """Transfer an ERC721 NFT from the victim wallet to a safe wallet."""
    return {
        "address": contract,
        "function_signature": "transferFrom(address,address,uint256)",
        "args": [from_victim, to, token_id],
        "gas_estimate": GAS_ERC721,
        "description": f"ERC721 token #{token_id} -> {to}",
    }


def transient_auction_house_erc721_rescue(
    auction_house: str,
    contract: str,
    from_victim: str,
    to: str,
    token_id: int,
) -> list[RescueData]:
    """Delist an escrowed ERC721 from Transient and transfer it to safety."""
    return [
        {
            "address": auction_house,
            "function_signature": "delist(address,uint256)",
            "args": [contract, token_id],
            "gas_estimate": GAS_TRANSIENT_DELIST,
            "description": f"Delist ERC721 token #{token_id} from Transient Auction House",
        },
        erc721_transfer(contract, from_victim, to, token_id),
    ]


def erc1155_transfer(
    contract: str, from_victim: str, to: str, token_id: int, amount: int
) -> RescueData:
    """Transfer ERC1155 tokens from the victim wallet to a safe wallet."""
    return {
        "address": contract,
        "function_signature": "safeTransferFrom(address,address,uint256,uint256,bytes)",
        "args": [from_victim, to, token_id, amount, b""],
        "gas_estimate": GAS_ERC1155,
        "description": f"ERC1155 token #{token_id} x{amount} -> {to}",
    }


def transfer_ownership(contract: str, to: str) -> RescueData:
    """Transfer ownership of a contract (Ownable) to a safe wallet."""
    return {
        "address": contract,
        "function_signature": "transferOwnership(address)",
        "args": [to],
        "gas_estimate": GAS_OWNERSHIP,
        "description": f"transferOwnership of {contract} -> {to}",
    }


def custom(
    contract: str, function_signature: str, args: list, gas_estimate: int = GAS_GENERIC
) -> RescueData:
    """Generic action: any function signature + args (power-user escape hatch)."""
    return {
        "address": contract,
        "function_signature": function_signature,
        "args": args,
        "gas_estimate": gas_estimate,
        "description": f"custom {function_signature} on {contract}",
    }
