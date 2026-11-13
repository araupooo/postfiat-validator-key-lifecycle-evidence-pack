# Claim-to-evidence index

Every headline claim in this pack, mapped to the repo file, field, and
line that holds it. Line numbers refer to the files as published in this
repository. Pinned tree: postfiatd main commit
`0085a1ff885d6a446369cf73a4430f75af22be55`. Harness:
`rotation_sim.py` 1.0.0, seed 20261113, 56 simulated days from
2026-11-13, validator set N=66 unless stated otherwise.

## Measured claims (from running the harness)

| # | Claim | Evidence |
|---|-------|----------|
| M-01 | Validator set size modelled is N=66, verified live from the PostFiat testnet explorer (ledger ~8,016,789) | `results/simulation_summary.json`, `config.validators_n`, line 9; `results/summary.txt`, line 3; explorer https://explorer.testnet.postfiat.org/network/validators (fetched 2026-11-13) |
| M-02 | Validation quorum = 45 of 66 under the 67% rule; 53 under the 80% rule | `results/simulation_summary.json`, `thresholds.postfiatd_validation_quorum` line 18 and `thresholds.upstream_validation_quorum` line 20; `results/threshold_table.csv`, header line 1 and N=66 rows lines 8-9 (`66,postfiatd-67pct,45,45,21,22,21` / `66,upstream-80pct,53,53,13,14,13`); `results/summary.txt`, line 5 |
| M-03 | Amendment minimum votes = 45 of 66 under the 67% rule; 53 under the 80% rule | Same as M-02: `thresholds.postfiatd_amendment_min_votes` line 19, `thresholds.upstream_amendment_min_votes` line 21; `threshold_table.csv` columns `amendment_min_votes`, lines 8-9 |
| M-04 | Compromise breaks quorum at k=22 compromised validators (67% rule) / k=14 (80% rule); 21 / 13 still tolerated | `results/compromise_sweep.csv`, header line 1 (`compromised_validators_k,...,quorum_reachable_67pct,...,quorum_reachable_80pct,...`); line 23 (`21,45,45,True,53,False,...` — 67% still reachable at 21) and line 24 (`22,44,45,False,53,False,...` — 67% breaks at 22); `results/summary.txt`, line 7; `results/threshold_table.csv`, columns `max_offline_tolerated` / `break_at_offline`, lines 8-9 |
| M-05 | Baseline staggered rotation (weekly batches of 9, 7-day overlap, 0-day delay): 0 validators without a trusted key on any day; quorum met every day under both rules | `results/rotation_schedule.csv`, column `validators_without_trusted_key` — every data row is 0; columns `quorum_met_67pct` / `quorum_met_80pct` contain no `False` in the file; `results/summary.txt`, line 9 |
| M-06 | Stress variant (2-day propagation delay, no overlap): worst day 9 validators without a trusted key; quorum still met every day | `results/stress/rotation_schedule.csv`, column `validators_without_trusted_key` — maximum 9 (day 0: `0,2026-11-13,9,9,9,57,45,True,53,True`); minimum `signing_validators` 57; no `False` in the file; `results/stress/summary.txt`, line 9 |
| M-07 | Single-validator mid-rotation failure (new manifest never trusted, 7-day recovery): 7 days without a trusted key; quorum intact (margins 20 at 67%, 12 at 80%) | `results/summary.txt`, line 11; `results/simulation_summary.json`, `config.recovery_days` line 15 (= 7) |
| M-08 | Fleet variant: quorum breaks at 22 simultaneous failures (67%) / 14 (80%) | Same break points as M-04: `results/compromise_sweep.csv`, lines 23-24; `results/summary.txt`, line 11 |
| M-09 | Coordinated whole-set rotation loses quorum for max(0, delay - overlap) days | `results/coordinated_rotation.csv`, all rows; e.g. delay 7 / overlap 0 -> 7 days without quorum (line 11: `7,0,7,True`); delay 7 / overlap 7 -> 0 days (line 13: `7,7,0,False`); `results/summary.txt`, line 15 |
| M-10 | Mixed network: old nodes lose quorum once 22 validators are hybrid-only (67%) / 14 (80%) | `results/mixed_network.csv`, header line 1 (`hybrid_only_validators_h,...,verifiable_by_old_nodes,...,old_nodes_reach_quorum_67pct,...,old_nodes_reach_quorum_80pct`); line 23 (`21,31.82,45,45,True,53,False` — 67% still reachable at 21) and line 24 (`22,33.33,44,45,False,53,False` — 67% breaks at 22); line 16 (`14,21.21,52,45,True,53,False` — 80% breaks at 14); `results/summary.txt`, line 13 |

## Source-derived claims (from the pinned tree and primary sources)

| # | Claim | Evidence |
|---|-------|----------|
| S-01 | Amendment majority threshold is 67/100 in postfiatd vs 80/100 upstream | Pinned tree: `include/xrpl/protocol/SystemParameters.h`, line 85: `constexpr std::ratio<67, 100> postFixAmendmentMajorityCalcThreshold;` (line 83 is the pre-fix 204/256 ratio). Upstream rippled 2.5.0, commit `1e01cd34f7a216092ed779f291b43324c167167a`, same file, line 147: `constexpr std::ratio<80, 100> postFixAmendmentMajorityCalcThreshold;`. Cited in `sources.md`, lines 58-63; `README.md`, lines 23-27; `key_lifecycle.md`, line 207; `assumptions.md`, line 15 |
| S-02 | Validation quorum formula is max(ceil(N x fraction), ceil(N x 0.60)); amendment minimum is floor(N x fraction) + 1 with a 2-week majority hold | Pinned tree: `src/xrpld/app/misc/detail/ValidatorList.cpp`, `ValidatorList::calculateQuorum` (67% quorum comment, 60% absolute-minimum floor); `include/xrpl/protocol/SystemParameters.h`, line 87 (`defaultAmendmentMajorityTime` = 2 weeks). Documented in `key_lifecycle.md`, lines 204-208; `assumptions.md`, line 15 |
| S-03 | Amendment-vote logic (`doVoting`) is byte-identical to upstream rippled 2.5.0; the threshold is the only divergence | `sources.md`, lines 58-63; `README.md`, lines 23-27 |
| S-04 | Two-tier validator keys: master key + ephemeral signing key; manifest carries a sequence number; sequence `0xFFFFFFFF` is a permanent revocation manifest | `key_lifecycle.md`, section 1, lines 9-35, with pinned-tree file:line citations in the text |
| S-05 | `[validator_token]` vs `[validation_seed]` are mutually exclusive; the seed path has no rotation (master key = signing key) | `key_lifecycle.md`, section 1.1, lines 36-62, with pinned-tree file:line citations in the text |
| S-06 | Validator-site refresh interval is 5 minutes | `key_lifecycle.md`, section 3.3, lines 176-189, with pinned-tree file:line citations in the text |
| S-07 | ML-DSA-65 sizes: public key 1,952 bytes, signature 3,309 bytes; 32-byte KeyGen seed | NIST FIPS 204, Table 2; documented in `key_lifecycle.md`, section 5.1, lines 223-237; `sources.md` |
| S-08 | No dual-signing state exists in the pinned code; the rotation overlap window is an operational procedure, not a protocol feature | `assumptions.md` (assumption A4); `key_lifecycle.md`, section 3 |
| S-09 | Whether PostFiat operators publish a domain attestation equivalent to XRPL's `xrp-ledger.toml`, and under what filename, is UNVERIFIED | `compromise_runbook.md`, section on domain attestation mismatch; `assumptions.md` (open questions) |

## Reproduction

Run `bash run_all.sh` from a fresh copy of this repository: it re-runs
the harness (baseline + stress), rebuilds `docs/index.html`, regenerates
`SHA256SUMS`, and verifies digests. Expected: exit 0, all derived outputs
byte-identical to the shipped files. See `REPRODUCTION.md` for the exact
command and recorded result. Verify digests at any time with
`bash verify_digests.sh --check`.
