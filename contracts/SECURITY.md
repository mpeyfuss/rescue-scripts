# EthRescue Security Notes

## Trust Model

- `RESCUER` is a clean EOA trusted to choose arbitrary zero-value calldata
  until the victim's EIP-7702 delegation is cleared.
- `SAFE` is immutable and distinct from `RESCUER`. Only native currency is
  contract-bound to it; asset destinations are encoded in action calldata.
- Balance and ownership postconditions determine whether an asset was rescued;
  a non-reverting call may still represent a protocol-level failure.
- The client supplies enough outer gas for all action stipends and contract
  overhead. Insufficient outer gas reverts the transaction.

## Static Analysis Triage

Slither reports the following intentional patterns:

- **Arbitrary ETH destination:** `_sweepEth` calls the constructor-bound,
  validated `SAFE`; no function accepts a replacement destination.
- **Low-level call:** forwarding the complete native balance to an arbitrary
  EOA or contract safe requires a low-level call and explicit success check.
- **Reentrancy during the native currency sweep:** the contract has no mutable
  storage, and a safe callback cannot pass the `RESCUER` check because both
  addresses must be distinct.
- **Unused call results:** `rescue` intentionally uses only the EVM success
  flag. `LibCall.tryCall` copies zero return bytes to bound hostile return data.
- **Compiler and naming warnings:** Solidity is pinned by the Foundry project;
  uppercase immutable names are intentional configuration constants.
