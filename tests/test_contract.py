from eth_abi import decode
from eth_utils import keccak, to_checksum_address

from eth_rescue import contract


def test_rescue_selector_matches_signature():
    assert (
        contract.RESCUE_SELECTOR
        == keccak(text="rescue((bool,address,uint256,bytes)[])")[:4]
    )


def test_build_deploy_data_appends_constructor_args():
    rescuer = "0x" + "11" * 20
    safe = "0x" + "22" * 20

    data = contract.build_deploy_data(rescuer, safe)

    assert data.startswith(contract.ETH_RESCUE_CREATION_BYTECODE)
    encoded = data[len(contract.ETH_RESCUE_CREATION_BYTECODE) :]
    decoded_rescuer, decoded_safe = decode(["address", "address"], encoded)
    assert to_checksum_address(decoded_rescuer) == to_checksum_address(rescuer)
    assert to_checksum_address(decoded_safe) == to_checksum_address(safe)


def test_encode_rescue_call_marks_all_actions_optional():
    prepared = [
        {"to": "0x" + "33" * 20, "data": "0xdeadbeef", "gas": 70_000},
        {"to": "0x" + "44" * 20, "data": "0x", "gas": 40_000},
    ]

    calldata = contract.encode_rescue_call(prepared)

    assert calldata[:4] == contract.RESCUE_SELECTOR
    (actions,) = decode(["(bool,address,uint256,bytes)[]"], calldata[4:])
    assert len(actions) == 2
    required, target, stipend, action_data = actions[0]
    assert required is False
    assert to_checksum_address(target) == to_checksum_address(prepared[0]["to"])
    assert stipend == 70_000
    assert action_data == bytes.fromhex("deadbeef")
    assert actions[1][3] == b""


def test_compute_create_address_matches_known_vector():
    # cast compute-address 0x1111...1111 --nonce 0
    address = contract.compute_create_address("0x" + "11" * 20, 0)
    assert address == "0x8F7a45eBDe059392E46A46DCc14AB24681A961Ea"
