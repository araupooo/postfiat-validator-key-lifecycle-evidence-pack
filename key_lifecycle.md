# Validator key lifecycle and rotation procedure

Codebase: postfiatd, commit `0085a1ff885d6a446369cf73a4430f75af22be55`
("Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9").
All file:line citations are to that tree. Numbers from the simulation
harness are in `results/simulation_summary.json`; assumptions the model
makes are in `assumptions.md`.

## 1. What a validator key is in this codebase

A validator has **two keys**, bound together by a manifest:

- **Master key** — the permanent validator identity. It never signs
  validations. It signs manifests.
- **Ephemeral signing key** — signs validations. It is the key peers
  verify validations against.

The binding object is the **manifest**: the master public key, the
ephemeral signing public key, a sequence number, an optional domain,
and signatures from both the master key and the ephemeral key
(`src/xrpld/app/misc/Manifest.h`, header comment, lines 30–79).
`ManifestCache` stores, per trusted validator, the most senior valid
manifest it has seen; a higher-sequence manifest supersedes the old
signing key. Sequence `0xFFFFFFFF` is a revocation manifest: it
supersedes any prior manifest, stores no new signing key, and no
further manifest for that master key is ever accepted — no validations
from that validator are accepted afterwards.

Only two key types exist in the tree: `secp256k1` and `ed25519`
(`include/xrpl/protocol/KeyType.h`). There is no post-quantum key
type. Both are forgeable under Shor's algorithm once a
cryptographically relevant quantum computer exists (see the sibling
crypto-inventory pack: 0 post-quantum mentions in the tree; production
validator signatures are Ed25519 and secp256k1/ECDSA).

### 1.1 How keys are loaded

`src/xrpld/app/misc/detail/ValidatorKeys.cpp` accepts exactly one of
two configuration forms, and refuses to start if both are present:

- `[validator_token]` — a base64 manifest plus a validation secret.
  The code derives a secp256k1 public key from the validation secret
  and requires it to equal the manifest's signing key; otherwise the
  configuration is invalid and the node fails to start. The node ID is
  computed from the master key, and the manifest sequence is recorded.
- `[validation_seed]` — a base58 seed. The code derives a secp256k1
  secret key from the seed, uses the same key as both master and
  signing key (`keys.emplace(pk, pk, sk)`), sets node ID from that key
  and sequence 0. There is **no manifest and no rotation path**: the
  identity is the signing key, so rotating it changes the validator
  identity. This form is the legacy path; the token form is the one
  that supports rotation.

Upstream documentation agrees: the `validator-keys` tool generates
keys and tokens offline, and a token is added as `[validator_token]`
in the server configuration (xrpl.org, "Run xrpld as a Validator").
The in-tree guide (`docs/ValidatorKeyUpdate.md`) documents the same
flow for this network: `validator-keys create_keys` (offline),
`validator-keys create_token` for a new signing key,
`validator-keys set_domain` for a domain change (which also generates
a new signing key).

### 1.2 Where the entropy comes from

Key material is derived from a 32-byte seed:

- `randomSecretKey()` (`src/libxrpl/protocol/SecretKey.cpp:299`)
  fills 32 bytes from `crypto_prng()`, the `csprng_engine`
  (`src/libxrpl/crypto/csprng.cpp`): OpenSSL `RAND_bytes` output,
  seeded by `RAND_poll` at construction plus `std::random_device`
  output mixed in with `RAND_add` at **zero entropy credit**
  (the code comments that it conservatively assumes the added data
  contributes no actual entropy).
- `generateSecretKey(KeyType, Seed)`: for Ed25519, the secret key is
  SHA-512Half of the seed; for secp256k1, a deterministic root-key
  derivation from the seed.

Entropy requirements for generation:

- **Classical keys**: 256 bits of entropy in the seed. The seed is the
  whole secret: anyone holding the 32-byte seed can re-derive the key.
  Treat seed material with the same safeguards as the private key
  itself.
- **ML-DSA keys (migration)**: ML-DSA key generation takes a 32-byte
  random seed ξ (`ML-DSA.KeyGen_internal(ξ)`, FIPS 204 §6) and expands
  it to the private key (2,560 / 4,032 / 4,896 bytes for ML-DSA-44 /
  -65 / -87). The 32-byte seed is therefore a sufficient backup
  representation, exactly as the 32-byte seed is for Ed25519 here —
  but it must be stored with the parameter set recorded alongside it,
  since the seed alone does not say which set it belongs to.

## 2. Custody

- **Master key (`validator-keys.json`)**: generate offline, on a
  machine that is not the validator. Store offline in at least two
  separate locations (encrypted USB, secure vault). Never store it on
  the validator host. The in-tree guide records a concrete hazard:
  the file lives inside the Docker container at
  `/root/.ripple/validator-keys.json` and **is deleted whenever the
  container is restarted or recreated** — back it up before any
  restart, and remove the local copy from the validator machine after
  backing up.
- **Signing key / validation secret**: lives on the validator only
  inside the `[validator_token]` value. It is replaceable without
  touching the master key.
- **Permissions**: key files readable by the owner only (mode 0600).
  The sibling inventory notes the codebase's own `random.h` documents
  the non-CSPRNG helpers as not cryptographically secure; only the
  CSPRNG path above feeds key material.
- **Backups**: after every token generation, back up the updated
  `validator-keys.json` — it now contains the new sequence number.
  Generating two tokens from the same backup without updating it
  reuses the same `token_sequence`, and the network ignores the later
  token (xrpl.org validator guide).

## 3. Rotation schedule

The in-tree guide recommends rotating the signing key every **6–12
months**, and immediately on suspected compromise, on hardware moves,
and on domain changes. The schedule below is built on that cadence
and on the harness results (`rotation_sim.py`, seed 20261113, 56
simulated days, N=66).

### 3.1 Staggered rotation (normal operation)

- Rotate the set in **weekly batches of ~1/8 of the validators**
  (9 of 66 per week), so a full set rotation completes in 8 weeks.
  Never rotate the whole set on one day: the coordinated-rotation
  grid (`results/coordinated_rotation.csv`) shows a same-day
  whole-set rotation loses quorum for `max(0, delay - overlap)` days
  if manifest propagation is delayed, while staggered rotation keeps
  quorum under both the 67% and the 80% rule even with a 2-day
  propagation delay (worst day: 9 of 66 validators without a trusted
  key; 57 signing vs quorum 45 at 67%, 53 at 80%).
- **Overlap / staged publication**: the pinned code has no
  dual-signing state — a manifest carries exactly one signing key, and
  a higher-sequence manifest supersedes the old key as soon as a peer
  sees it. The overlap window is therefore an operational procedure,
  not a protocol feature:
  1. Generate the new signing key and manifest **offline** with the
     master key (sequence = old sequence + 1).
  2. Publish the new manifest to the validator-list site / gossip
     network **at least 7 days before** activating it, and verify it
     is visible on peers (manifest cache / explorer) before proceeding.
     The validator keeps signing with the old key in the meantime,
     because it has not restarted with the new token.
  3. Restart the validator with the new `[validator_token]`. From
     that moment it signs only with the new key, which peers already
     trust.
  4. Confirm the validator's validations are accepted (ledger closes
     include it; check the validator's signing-key status on the
     explorer) before the next batch rotates.
- With a 7-day overlap, the harness shows **zero** days without a
  trusted key even if propagation takes 7 days; with no overlap, a
  2-day propagation delay leaves each rotating validator without a
  trusted key for 2 days.

### 3.2 Rollback

- **Signing-key rollback**: publish a new manifest with a higher
  sequence number that reinstates the previous signing key (or a fresh
  one), signed by the master key. Peers accept the highest-sequence
  valid manifest, so the rollback is the same operation as a rotation.
  There is no "undo" — only a forward sequence number.
- **Master-key compromise**: publish a revocation manifest
  (sequence `0xFFFFFFFF`, no signing key), loaded from
  `[validator_key_revocation]` and gossiped to peers. That identity is
  permanently dead; recovery means creating a **new validator
  identity** (new master key) and getting it added to UNL publisher
  lists — a coordination task, not a key operation.
- **Sequence-number exhaustion**: at most 4,294,967,293 tokens per
  master key pair (in-tree guide). At one rotation per 6 months this
  is not a practical limit; it matters only as a reason never to burn
  sequences in automated retries.

### 3.3 Propagation timing (verified from source)

- Validator-list sites are fetched on a **5-minute** default refresh
  interval, with a 30-second retry on error
  (`src/xrpld/app/misc/detail/ValidatorSite.cpp:34-35`). Manifest
  gossip between peers is faster than the site refresh in the normal
  case. The harness baseline (0-day propagation delay) is therefore
  the realistic case; multi-day delays are stress cases, e.g. a
  validator-list site outage or a partition.
- Amendment votes expire **24 hours** after a validator's last
  validation (`AmendmentTable.cpp`, `TrustedVotes::recordVotes`).
  A validator offline for a full day has no live amendment vote,
  which is why the harness counts outages in whole days.

## 4. Thresholds that bound every rotation decision

For a validator set of size N (N=66 is the count listed by the
PostFiat testnet explorer on 2026-11-13, ledger ~8,016,789; the set
changes over time, so re-check it before planning):

| Quantity | postfiatd (67%) | upstream rippled (80%) |
|---|---|---|
| Validation quorum, N=66 | 45 | 53 |
| Amendment minimum votes, N=66 | 45 | 53 |
| Max compromised/offline tolerated, N=66 | 21 | 13 |
| Break point (compromised/offline), N=66 | 22 | 14 |

Formulas (verified by reading + arithmetic; see RESEARCH.md):
validation quorum = `max(ceil(N × fraction), ceil(N × 0.60))`
(`ValidatorList::calculateQuorum`); amendment minimum =
`floor(N × fraction) + 1`, with a 2-week majority hold before enabling
(`AmendmentTable::computeThreshold` / `passes`, `SystemParameters.h:85`).
Full table for N = 16, 25, 53, 66 in `results/threshold_table.csv`.

Consequences for rotation planning:

- A rotation batch must stay well under 21 validators (at N=66):
  the harness fleet variant breaks quorum at 22 simultaneous
  failures. A 9-validator batch failing at once leaves 57 signing
  validators: margin 12 at the 67% rule (57 − 45) and margin 4 at the
  80% rule (57 − 53). Plan batches against the **80%** rule, not
  the 67% rule: the in-tree quorum comment says the 67% value is for
  devnet/testnet and "for mainnet, this should be reverted to 80%".
- A single validator's rotation failure is survivable: 7 days without
  a trusted key (the harness failure scenario, recovery after 7 days)
  leaves quorum intact with margin 20 at 67% and 12 at 80%.

## 5. ML-DSA migration path

### 5.1 Sizes (FIPS 204, Table 2)

| Parameter set | Category | Private key | Public key | Signature |
|---|---|---|---|---|
| ML-DSA-44 | 2 | 2,560 B | 1,312 B | 2,420 B |
| ML-DSA-65 | 3 | 4,032 B | 1,952 B | 3,309 B |
| ML-DSA-87 | 5 | 4,896 B | 2,592 B | 4,627 B |

For comparison: Ed25519 public key 32 bytes, signature 64 bytes
(RFC 8032). An ML-DSA-65 signature is ~52× an Ed25519 signature and
its public key ~61× larger. ML-DSA-65 is the general-purpose default;
ML-DSA-87 is the CNSA 2.0 selection for national-security systems.

### 5.2 Mixed-network operation

The migration must run while classical and post-quantum validators
coexist, because a flag-day switch of the whole set is not possible
(coordinated rotation already breaks quorum if propagation lags; a
flag day is the same failure mode with no fallback).

- **Phase A — dual-signed (hybrid) validators.** Each validator
  carries both a classical signing key and an ML-DSA signing key and
  signs each validation twice. Old nodes verify the classical half;
  new nodes verify both. Dual-signed validators count toward quorum
  for old and new nodes alike, so this phase costs nothing in quorum
  terms. This requires a manifest format that can carry two signing
  keys — **not present in the pinned code** (one `signingKey` per
  manifest) and an open design question: how the second key is
  encoded, and how old nodes treat a manifest they cannot fully
  parse.
- **Phase B — hybrid-only validators.** Once a validator drops its
  classical key it becomes unverifiable to old nodes. The harness
  (`results/mixed_network.csv`) bounds this: old nodes lose quorum
  once **22** validators are hybrid-only at N=66 under the 67% rule
  (14 under the 80% rule). Keep the hybrid-only count below that
  bound until old nodes have upgraded; the binding constraint is the
  80% rule (14), not the 67% rule.
- **Phase C — retirement.** Retire classical-only verification by
  amendment (67% majority in this codebase, 2-week hold) only after a
  measured supermajority of the set is hybrid. Retirement is its own
  amendment with its own activation time, never a flag day.

### 5.3 Code changes required (from the pinned tree)

1. Extend `KeyType` (`include/xrpl/protocol/KeyType.h`) with an
   ML-DSA entry; the enum currently has only `secp256k1` and
   `ed25519`, and `generateSecretKey` / `derivePublicKey` have no
   branch for a third type.
2. Extend the manifest format with a second signing key (or a second
   manifest type) for the hybrid phase; add a new Base58Check version
   prefix for ML-DSA keys (public keys are 1,952 bytes at ML-DSA-65,
   not 32).
3. Gate activation behind a ledger amendment under the 67% rule, with
   the 2-week hold; the amendment-vote machinery itself is
   byte-identical to upstream rippled 2.5.0.
4. Measure first: ML-DSA-65 validations are ~3.3 kB each; the effect
   on validation throughput, ledger size, and peer bandwidth must be
   measured before enabling, and the manifest/validation size limits
   in the code must be checked against the new sizes. **Open
   question**: the exact size limits and fee/throughput impact are not
   established in this pack — they need a measurement run, not an
   estimate.

### 5.4 What does not change

- The master-key / manifest indirection stays: the ML-DSA key is a
  new **signing** key, vouchsafed by the same classical master key
  until the master key itself migrates. A post-quantum master key
  (ML-DSA or SLH-DSA) is a later step; SLH-DSA's hash-only security
  assumption makes it the conservative choice for the long-lived
  master key, at 7,856–49,856-byte signatures (FIPS 205) that are
  acceptable for the rare manifest-signing operation.
- The CSPRNG stays the entropy source (`csprng.cpp`); re-audit its
  seeding before it feeds ML-DSA key generation at scale, since every
  post-quantum key will depend on it.
