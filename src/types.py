from typing import TypedDict


class RescueData(TypedDict):
    address: str
    function_signature: str
    args: list[any]
    gas_estimate: int
