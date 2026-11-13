# Assumptions register — verified from source vs assumed

Every claim in this pack is either verified from the pinned tree or a
primary standard, or it is an assumption listed here. Nothing in the
"assumed" column is presented as a measured fact elsewhere in the pack.

## Verified from the pinned tree (postfiatd 0085a1ff)

| Fact | Source in the tree |
|---|---|
| Only two key types exist: `secp256k1`, `ed25519` | `include/xrpl/protocol/KeyType.h` |
| Validator identity = master key; validations signed by an ephemeral signing key bound by a manifest with a sequence number; higher sequence supersedes; sequence `0xFFFFFFFF` revokes permanently | `src/xrpld/app/misc/Manifest.h`, header comment lines 30–79 |
| `[validator_token]` and `[validation_seed]` are mutually exclusive; token path derives a secp256k1 key from the validation secret and requires it to equal the manifest signing key; seed path uses the same secp256k1 key as master and signing key, sequence 0 | `src/xrpld/app/misc/detail/ValidatorKeys.cpp` |
| Validation quorum = `max(ceil(0.67 × effective UNL), ceil(0.60 × UNL))`; comment says upstream uses 80% and this fork uses 67% for devnet/testnet, reverting to 80% for mainnet | `src/xrpld/app/misc/detail/ValidatorList.cpp`, `calculateQuorum` (~line 1898) |
| Amendment majority (post-fix) = votes > `floor(N × 67/100)`; 2-week majority hold; vetoed amendments can never gain majority; votes expire 24 h after a validator's last validation | `include/xrpl/protocol/SystemParameters.h:85`; `src/xrpld/app/misc/detail/AmendmentTable.cpp` (`computeThreshold`, `passes`, `doVoting`, `TrustedVotes::recordVotes`) |
| `doVoting` is byte-identical to upstream rippled 2.5.0; the only divergence is the 67/100 vs 80/100 threshold | `~/workspace/postfiatd-amendment/RESEARCH.md` (amendment-vote research notes, Nov 2026) |
| Validator-list sites refresh every 5 minutes by default, 30-second retry on error | `src/xrpld/app/misc/detail/ValidatorSite.cpp:34-35` |
| CSPRNG: OpenSSL `RAND_bytes`, `RAND_poll` at construction, `std::random_device` mixed in at zero entropy credit | `src/libxrpl/crypto/csprng.cpp` |
| Random secret keys are 32 bytes from the CSPRNG; Ed25519 secret key = SHA-512Half of the seed; secp256k1 secret key = deterministic root-key derivation from the seed | `src/libxrpl/protocol/SecretKey.cpp` (`randomSecretKey`, `generateSecretKey`) |
| No post-quantum algorithm appears anywhere in the tree (0 matches); TLS via pinned OpenSSL 1.1.1w; no key agreement in the ledger protocol itself | Sibling crypto-inventory pack (`summary.json`, `exposure_matrix.md`, `call_sites.md`) over the same pinned tree |
| Rotation recommended every 6–12 months; at most 4,294,967,293 tokens per master key; `validator-keys.json` is deleted on container restart; manifest propagation "within minutes" | `docs/ValidatorKeyUpdate.md` (in-tree guide) |

## Verified from primary standards / live sources

| Fact | Source |
|---|---|
| ML-DSA-44/65/87 sizes: public keys 1,312/1,952/2,592 B; private keys 2,560/4,032/4,896 B; signatures 2,420/3,309/4,627 B; categories 2/3/5 | NIST FIPS 204, Tables 1–2 (13 Aug 2024) |
| ML-DSA key generation takes a 32-byte random seed ξ | FIPS 204 §6 (`ML-DSA.KeyGen_internal(ξ)`); OpenSSL 3.5 `EVP_PKEY-ML-DSA` documentation |
| Ed25519 public key 32 B, signature 64 B | RFC 8032 |
| SLH-DSA signatures 7,856–49,856 B; security rests only on hash functions | NIST FIPS 205 |
| Shor breaks RSA/DH/ECDH/ECDSA/EdDSA; Grover halves symmetric/hash strength | Shor 1997 (arXiv:quant-ph/9508027); Grover 1996 (arXiv:quant-ph/9605043) |
| `validator-keys create_keys` / `create_token`; token-sequence reuse is ignored by the network; `[validator_token]` in server config | xrpl.org, "Run xrpld as a Validator" |
| Testnet validator count N=66, ledger ~8,016,789, version 1.0.9 dominant, on 2026-11-13 | PostFiat testnet explorer, https://explorer.testnet.postfiat.org/network/validators, fetched 2026-11-13 22:40 WIB |

## Assumed (model inputs, not measured facts)

| # | Assumption | Why it is assumed, and what would change the result |
|---|---|---|
| A1 | Validator-set size N=66. | Snapshot from the explorer on 2026-11-13; the set changes as validators join/leave. The harness also computes N=16, 25, 53 (threshold table) so the break points can be re-read for any set size. |
| A2 | The explorer's "UNL Count 25" is modelled as a sensitivity case (N=25), not as a confirmed UNL size. | The explorer header reports "Validators, 66, UNL Count, 25" without defining UNL Count. It may be the number of UNLs the explorer tracks, or a per-node UNL size. Until its meaning is confirmed, N=25 is a what-if, and the default remains N=66. |
| A3 | A validator in manifest transition (new manifest published, not yet trusted network-wide) counts as NOT signing. | Conservative counting choice. In reality, during propagation some peers trust the new key and some still trust the old one, so the validator's validations are accepted by a fraction of the network. The conservative choice overstates outage, never understates it. |
| A4 | The "overlap window" is an operational procedure (publish the manifest early, activate late), not a protocol feature. | The pinned code has no dual-signing state: a manifest carries exactly one signing key. The harness models the overlap as the pre-publication lead; if operators instead restart with the new token immediately, the overlap is 0 and the transition gap equals the propagation delay. |
| A5 | UNL / manifest propagation is modelled as a single delay in whole days. | The code's site refresh is 5 minutes, so the realistic delay is minutes (0 days in the model). Multi-day delays are stress cases (site outage, partition). The model does not simulate per-peer gossip timing. |
| A6 | Compromised validators lose their votes entirely. | Covers both revocation and adversarial voting, which share the same quorum arithmetic (only honest votes count). The model does not simulate double-signing / equivocation detection, negative-UNL exclusion dynamics, or the fork-safety interaction between two UNLs with partial overlap (Theorem 8, arXiv:1802.07242). |
| A7 | Amendment votes are not simulated with 24-hour expiry. | Modelled outages are counted in whole days; any validator offline for a full day has no live vote anyway, so expiry does not change the break points. |
| A8 | Mixed-network accounting: an old node's quorum is still computed over its full UNL of N, while its verifiable set shrinks by the hybrid-only count. | Follows from `calculateQuorum` (quorum from UNL size) plus the fact that an old node cannot verify a signature it has no algorithm for. Unverified in code: how an old node actually treats a manifest/validation carrying an unknown key type (reject, ignore, or fail to parse) is an open design question, not a measured behaviour. |
| A9 | The ledger was not compiled or run. | A full build is not feasible on the audit machine (no Conan, ~1 GB RAM available). All code claims are from reading the pinned tree; the harness models the mechanics as read, and the arithmetic was checked against the AmendmentTable test fixtures (16 validators, 11/16 majority at 67%). |

## Open questions (not settled by the tree, the standards, or this pack)

1. **Hybrid manifest encoding.** How a manifest carries a second (ML-DSA) signing key, and how old nodes treat it, is not specified anywhere. It must be designed, not adopted.
2. **Old-node behaviour on unknown key types.** Reject, ignore, or parse-failure — unverified; it decides whether assumption A8 is exactly right.
3. **ML-DSA parameter set.** ML-DSA-65 (general-purpose default) vs ML-DSA-87 (CNSA 2.0) is not decided; it trades 3,309 vs 4,627-byte signatures against security category 3 vs 5.
4. **Validation throughput / ledger-size impact** of ~3.3 kB ML-DSA-65 signatures, and the manifest/validation size limits in the code. Needs a measurement run.
5. **Meaning of the explorer's "UNL Count 25"** (see A2).
6. **Compromise detection.** No detector exists in the tree; detection is procedural (sequence-number and signing-key comparison by the operator).
