from typing import Any, List, Optional, Union, cast
from flashbots.flashbots import Flashbots
from flashbots.types import FlashbotsOpts
from flashbots.middleware import construct_flashbots_middleware
from flashbots.provider import FlashbotProvider
from hexbytes import HexBytes
from web3 import Web3
from eth_account.signers.local import LocalAccount
from eth_typing import URI
from web3._utils.module import attach_modules

BUILDERS = [
    "flashbots",
    "rsync",
    "beaverbuild.org",
    "builder0x69",
    "Titan",
    "payload",
    "bobthebuilder",
]


class FlashbotsMP(Flashbots):
    def send_raw_bundle_munger(
        self,
        signed_bundled_transactions: List[HexBytes],
        target_block_number: int,
        opts: Optional[FlashbotsOpts] = None,
    ) -> List[Any]:
        resp = super().send_raw_bundle_munger(
            signed_bundled_transactions, target_block_number, opts
        )
        resp[0]["builders"] = BUILDERS
        return resp


class FlashbotsWeb3(Web3):
    flashbots: FlashbotsMP


def flashbot(
    w3: Web3,
    signature_account: LocalAccount,
    endpoint_uri: Optional[Union[URI, str]] = None,
) -> FlashbotsWeb3:
    flashbots_provider = FlashbotProvider(signature_account, endpoint_uri)
    flash_middleware = construct_flashbots_middleware(flashbots_provider)
    w3.middleware_onion.add(flash_middleware)

    # attach modules to add the new namespace commands
    attach_modules(w3, {"flashbots": (FlashbotsMP,)})

    return cast(FlashbotsWeb3, w3)
