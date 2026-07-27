"""
Functions for string to abi encoded hex
"""

from typing import Any

from eth_abi import encode as abi_encode, is_encodable_type
from eth_abi.grammar import parse
from eth_utils import function_signature_to_4byte_selector


def _parse_types(function_signature: str) -> list[str]:
    """
    Extract the parameter types from a function signature such as
    `transferFrom(address,address,uint256)`.
    """
    start = function_signature.index("(")
    end = function_signature.rindex(")")
    param_str = function_signature[start : end + 1].strip()
    if param_str == "()":
        return []
    types = [param.to_type_str() for param in parse(param_str).components]
    invalid_types = [t for t in types if not is_encodable_type(t)]
    if len(invalid_types) > 0:
        raise ValueError(
            f'The following invalid types were found in "{function_signature}": {invalid_types}'
        )
    return types


def build_calldata(function_signature: str, args: list[Any]) -> str:
    """
    Build ABI-encoded calldata for `function_signature` with `args`.
    `args` are expected to be valid python types that don't need to be coerced.
    """
    selector = function_signature_to_4byte_selector(function_signature)
    types = _parse_types(function_signature)
    if len(types) != len(args):
        raise ValueError(
            f"{function_signature} expects {len(types)} args, got {len(args)}"
        )
    encoded = abi_encode(types, args)
    return "0x" + (selector + encoded).hex()
