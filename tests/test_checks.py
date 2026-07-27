from types import SimpleNamespace

from eth_rescue import checks

SAFE = "0x000000000000000000000000000000000000BEEF"
OTHER = "0x000000000000000000000000000000000000dEaD"
TOKEN = "0x0000000000000000000000000000000000000001"


def _erc20(amount):
    return {
        "address": TOKEN,
        "function_signature": "transfer(address,uint256)",
        "args": [SAFE, amount],
    }


class FakeFunctions:
    def __init__(self, results):
        self._results = results

    def balanceOf(self, *args):
        return SimpleNamespace(call=lambda: self._results["balanceOf"](*args))

    def ownerOf(self, token_id):
        return SimpleNamespace(call=lambda: self._results["ownerOf"](token_id))

    def owner(self):
        return SimpleNamespace(call=lambda: self._results["owner"]())


class FakeContract:
    def __init__(self, results):
        self.functions = FakeFunctions(results)


def _fake_w3(results):
    return SimpleNamespace(
        eth=SimpleNamespace(contract=lambda address, abi: FakeContract(results))
    )


def test_infer_check_maps_known_signatures():
    assert checks.infer_check(_erc20(5)).kind == "erc20"
    assert (
        checks.infer_check(
            {
                "address": TOKEN,
                "function_signature": "transferFrom(address,address,uint256)",
                "args": [OTHER, SAFE, 9],
            }
        ).kind
        == "erc721"
    )
    assert (
        checks.infer_check(
            {
                "address": TOKEN,
                "function_signature": "transferOwnership(address)",
                "args": [SAFE],
            }
        ).kind
        == "ownership"
    )


def test_infer_check_unknown_signature_returns_none():
    assert (
        checks.infer_check(
            {
                "address": TOKEN,
                "function_signature": "delist(address,uint256)",
                "args": [],
            }
        )
        is None
    )


def test_evaluate_erc20_uses_snapshot_delta():
    rescue_data = [_erc20(100)]
    checks_map = checks.infer_checks(rescue_data)
    balances = {"balanceOf": lambda account: 250}
    w3 = _fake_w3(balances)
    snapshot = {0: 200}

    outcomes = checks.evaluate_checks(w3, checks_map, snapshot, 1)
    assert outcomes[0].status == "failed"  # only +50 received, needed 100

    balances["balanceOf"] = lambda account: 300  # +100 received
    outcomes = checks.evaluate_checks(w3, checks_map, snapshot, 1)
    assert outcomes[0].status == "rescued"


def test_evaluate_erc721_checks_owner():
    rescue_data = [
        {
            "address": TOKEN,
            "function_signature": "transferFrom(address,address,uint256)",
            "args": [OTHER, SAFE, 9],
        }
    ]
    checks_map = checks.infer_checks(rescue_data)

    w3 = _fake_w3({"ownerOf": lambda token_id: SAFE})
    assert checks.evaluate_checks(w3, checks_map, {}, 1)[0].status == "rescued"

    w3 = _fake_w3({"ownerOf": lambda token_id: OTHER})
    assert checks.evaluate_checks(w3, checks_map, {}, 1)[0].status == "failed"


def test_evaluate_unknown_action_is_unverified():
    rescue_data = [
        {"address": TOKEN, "function_signature": "delist(address,uint256)", "args": []}
    ]
    checks_map = checks.infer_checks(rescue_data)
    outcomes = checks.evaluate_checks(_fake_w3({}), checks_map, {}, 1)
    assert outcomes[0].status == "unverified"


def test_evaluate_treats_rpc_error_as_failure():
    rescue_data = [
        {
            "address": TOKEN,
            "function_signature": "transferOwnership(address)",
            "args": [SAFE],
        }
    ]
    checks_map = checks.infer_checks(rescue_data)

    def boom():
        raise RuntimeError("no owner()")

    outcomes = checks.evaluate_checks(_fake_w3({"owner": boom}), checks_map, {}, 1)
    assert outcomes[0].status == "failed"
