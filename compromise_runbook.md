# Compromise-response runbook: suspected validator-key compromise

Codebase: postfiatd, commit `0085a1ff885d6a446369cf73a4430f75af22be55`.
All file:line citations are to that tree. All numbers below come from
`results/simulation_summary.json` (harness `rotation_sim.py`, seed
20261113, N=66) unless stated otherwise. Assumptions are in
`assumptions.md`.

## 0. Which key is compromised? (decides everything)

| Case | What the attacker holds | Blast radius |
|---|---|---|
| A. Signing (ephemeral) key only | The validation secret in `[validator_token]` | That validator's validations can be forged until a higher-sequence manifest supersedes the key. The master key is safe. |
| B. Master key | `validator-keys.json` (master secret) | The attacker can issue manifests for that validator identity, including revoking it. The identity is permanently untrustworthy. |
| C. Seed-form validator (`[validation_seed]`) | The seed | Master key = signing key (ValidatorKeys.cpp: the seed path sets both to the same key). Cases A and B collapse into one: the whole identity is compromised. |

Distinguish A from B first: if the master key file is intact, offline,
and its access log shows no exposure, treat it as case A. If the master
key file, its backup, or the offline machine is exposed, treat it as
case B. When in doubt, treat it as B — the cost of overreacting is one
validator identity; the cost of underreacting is forged validations
under a trusted identity.

## 1. Detection

Signals, in the order they usually appear:

1. **Unexpected manifest sequence jump.** `ManifestCache` keeps the
   highest-sequence valid manifest per validator. A manifest with a
   sequence number higher than the operator's own last issued sequence
   means someone else used the master key — case B. Check the
   operator's own sequence log against the sequence peers report.
2. **Conflicting validations.** Two different validations for the same
   ledger from the same signing key, or validations that do not match
   the ledger the validator actually built. A signing key signs every
   validation the validator emits; a forged validation is
   indistinguishable from a real one by signature alone, so look for
   validations the operator's node did not emit (compare against the
   node's own log).
3. **Validations from a superseded key.** After a rotation, validations
   signed by the old key should stop. If they continue, the old key is
   in someone else's hands.
4. **Domain attestation mismatch.** The manifest carries a domain.
   In upstream XRPL, a validator operator publishes an attestation at
   `https://<domain>/.well-known/xrp-ledger.toml`; a manifest whose
   domain attestation the operator did not publish is suspect. The
   pinned postfiatd tree contains no reference to such a file, so
   whether PostFiat operators publish an equivalent attestation — and
   under what filename — is UNVERIFIED and is recorded as an open
   question; do not assume the filename.
5. **Peer reports / explorer anomalies.** The validator appears on the
   explorer with a new signing key the operator did not issue, or
   peers report manifest verification failures for that validator.

Detection gaps, stated honestly: nothing in the pinned code alerts on
any of the above automatically — there is no compromise detector in
the tree. Detection depends on the operator comparing the sequence
number and signing key peers see against their own records. The
24-hour amendment-vote expiry (`TrustedVotes`, `AmendmentTable.cpp`)
bounds how long a stale vote lingers, but it does not detect forgery.

## 2. Containment

### Case A — signing key compromised, master key safe

1. **Stop the validator.** It is signing with a key the attacker also
   holds; every further validation it emits is deniable.
2. **Generate a new signing key and manifest offline** with the master
   key: `validator-keys create_token` (sequence = old + 1). The new
   manifest supersedes the compromised key as soon as peers see it.
3. **Publish the new manifest and restart with the new token.**
   Propagation is minutes-scale in the normal case (validator-site
   refresh 5 minutes). Verify peers accept the new signing key before
   considering the validator back.
4. **Do not reuse the sequence number.** A token generated from a
   stale backup of `validator-keys.json` reuses the old sequence and
   is ignored by the network.

### Case B — master key compromised

1. **Stop the validator.**
2. **Publish a revocation manifest** (sequence `0xFFFFFFFF`, no
   signing key) via `[validator_key_revocation]` and gossip. From the
   moment peers see it, no validation from that master key is accepted
   — the identity is dead, permanently, because no higher sequence
   number exists.
3. **Create a new validator identity** (new master key, new
   `validator-keys.json`, new token). This is a new validator as far
   as the network is concerned: it must be added to UNL publisher
   lists before other nodes trust it. There is no in-protocol shortcut.
4. **Audit the exposure**: every backup copy of the old
   `validator-keys.json`, every machine that held it, every operator
   who had access.

### Case C — seed-form validator compromised

Same as case B: the identity is dead. Migrate to the token form when
recreating the validator, so the next rotation does not require a new
identity.

### Network-level containment (any case)

- **UNL publisher removal**: the validator's key can be removed from
  the publisher lists that feed `ValidatorList`. Removal propagates
  on the next list fetch (5-minute default refresh).
- **Negative UNL**: the negative-UNL protocol can exclude a validator
  from the effective UNL; the absolute-minimum quorum floor is 60%
  of the original UNL size, so exclusion never drops the quorum
  below that floor.
- **What containment cannot do**: it cannot un-sign validations the
  attacker already emitted, and it cannot retroactively remove the
  attacker's votes from ledgers already closed. The ledger's defence
  is the quorum arithmetic in §4, not revocation speed.

## 3. Recovery

1. **Case A**: new signing key + manifest (steps above). Expected
   downtime: minutes if a fresh manifest is ready, longer if the
   operator must first regain access to the offline master key. The
   harness models a 7-day recovery: the validator has no trusted
   signing key for 7 days, and quorum still holds (margin 20 at 67%,
   12 at 80% — see worked example A).
2. **Case B/C**: new identity + UNL re-listing. Downtime is set by
   the UNL publisher process, not by key generation; treat it as days,
   not minutes, and do not promise a time the publisher process does
   not support.
3. **After recovery**: back up the updated `validator-keys.json`
   (new sequence number), verify the validator's validations are
   accepted, and record the incident: date, which key, sequence
   numbers before/after, revocation manifest hash if any.
4. **Post-incident rotation**: rotate the signing key again on a
   short fuse (days, not months) to confirm the new key pipeline
   works end to end.

## 4. Worked examples (N=66, from the harness)

Thresholds: validation quorum 45 (67% rule) / 53 (80% rule);
amendment minimum votes 45 / 53. Full sweeps in
`results/compromise_sweep.csv` and `results/threshold_table.csv`.

### Example A — one signing key compromised (case A)

- Compromised: k=1. Honest validators: 65. Quorum 45 reachable with
  margin 20 (67% rule), margin 12 (80% rule).
- The validator is offline (stopped) for 7 days while the operator
  republishes a manifest: 7 days without a trusted signing key
  (`rotation_failure_single`), quorum intact throughout.
- Amendment votes: the validator's vote expires 24 hours after its
  last validation, so its absence costs nothing beyond one vote.
- **Verdict: survivable with no network impact.** The risk is
  operational (how fast the operator notices and republishes), not
  consensus.

### Example B — one master key compromised (case B)

- Same arithmetic as A (k=1, margin 20/12), but the identity is
  permanently dead: revocation manifest `0xFFFFFFFF` removes it from
  the trusted set. The set is now effectively N=65 until a new
  identity is listed: quorum at N=65 is `ceil(65 × 0.67)` = 44, and
  the network keeps closing ledgers throughout.
- The cost is the re-listing coordination, not quorum.

### Example C — how many compromised validators break the network

| Compromised k | Honest | Quorum reachable (67%) | Quorum reachable (80%) |
|---:|---:|:---:|:---:|
| 1 | 65 | yes (margin 20) | yes (margin 12) |
| 13 | 53 | yes (margin 8) | yes (margin 0) |
| 14 | 52 | yes (margin 7) | **no** |
| 21 | 45 | yes (margin 0) | no |
| 22 | 44 | **no** | no |

- Under the 67% rule the network keeps closing ledgers until **22**
  validators are compromised; under the 80% rule it breaks at **14**.
  The same break points apply to amendment majorities, because at
  N=66 the amendment minimum (45) equals the validation quorum (45).
- **Blast-radius bound**: an attacker who compromises signing keys
  must compromise 22 of 66 validators (a third of the set) to halt
  the network under the 67% rule, and 14 under the 80% rule. The 67%
  quorum tolerates more compromise but also tolerates more Byzantine
  validators (t ≤ 0.33·N per the quorum comment's Theorem 8 bound):
  the lower quorum buys liveness at the price of fork-safety margin.
  The in-tree comment says the 67% value is for devnet/testnet and
  should revert to 80% for mainnet — plan incident response against
  the 80% numbers.
- **Equivocation note**: the model counts compromised validators as
  losing their votes. An attacker who instead uses compromised keys
  to vote *against* the honest majority, or to double-sign, does not
  change the quorum arithmetic (the honest votes are what matter),
  but double-signing evidence is detectable by comparing validations
  — that is a detection input, not a separate break point. The model
  does not simulate equivocation detection; see `assumptions.md`.

### Example D — fleet-wide bad rotation (22 simultaneous failures)

- A faulty tooling release rotates 22 validators at once and every
  new manifest fails to propagate: 44 signing validators remain,
  quorum 45 is not met, and the network stops closing ledgers until
  the manifests are republished.
- Recovery: republish the manifests (or roll back to the previous
  signing keys with higher-sequence manifests) one batch at a time;
  quorum returns as soon as the 45th validator is signing again.
  This is why the rotation procedure staggers batches of 9 and
  verifies each batch before the next: a single bad batch (9) leaves
  margin 12 at 67% and margin 4 at 80%.

## 5. Checklist (copy per incident)

- [ ] Which key: signing / master / seed-form (case A / B / C).
- [ ] Validator stopped (time recorded).
- [ ] Sequence numbers: operator's last issued vs what peers report.
- [ ] Containment: new manifest published (case A) or revocation
      manifest published (case B/C) — hash recorded.
- [ ] UNL publisher notified if the identity is dead.
- [ ] Recovery: new token installed, validations accepted (verified
      on explorer / peer logs).
- [ ] `validator-keys.json` backed up with the new sequence number.
- [ ] Incident record written: dates, keys, sequences, hashes.
