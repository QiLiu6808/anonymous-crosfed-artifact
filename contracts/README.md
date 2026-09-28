# CrosFed contracts

The four deployed contracts correspond to the four manuscript procedures:

- `EncryptedUpdateRegistry.sol`: upload encrypted local updates (Algorithm 1).
- `EncryptedUpdateRelay.sol`: signed request/response state for retrieving encrypted updates (Algorithm 2).
- `PartialUpdateRegistry.sol`: upload partial global updates (Algorithm 3).
- `PartialUpdateRelay.sol`: signed request/response state for retrieving partial updates (Algorithm 4).

The two upload registries support the manuscript-faithful inline payload mode. For full model deployments, a content-addressed adapter may submit a canonical manifest as `payload`; measurements must label this mode separately from inline ciphertext storage.

Signature verification is split between the ChainMaker account layer/relay and the application envelope verifier. The contracts enforce SHA-256 payload hashes, unique submitters or requests, round-context keys, authorized response relayers, and immutable transaction records. The current HMAC provider is simulation-only; production deployment must bind `signerId` to a ChainMaker certificate/account and use its public-key signature suite.

Compile all contracts with `bash scripts/compile_contracts.sh`. Deploy the
institution registry, aggregator registry, and both relay contracts to their
respective chains with `bash scripts/deploy_chainmaker_multichain.sh <cmc>
<institution-sdk> <aggregator-sdk> <relay-sdk>`.
