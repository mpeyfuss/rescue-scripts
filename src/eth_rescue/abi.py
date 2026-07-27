"""
Minimal ABIs for contract reads post rescue
"""

ERC721_OWNER_OF_ABI = [
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"name": "owner", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

ERC20_BALANCE_OF_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

ERC1155_BALANCE_OF_ABI = [
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"},
        ],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

OWNABLE_OWNER_ABI = [
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"name": "owner", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]
