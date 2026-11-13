# PostFiat Ledger — Validator Key Lifecycle and Rotation Simulation

A rotation-simulation harness and key-lifecycle documentation for the
postfiatd validator set, grounded in the pinned source tree. The
harness models the validator-set mechanics in that tree — validation
quorum, amendment majority, manifest-based key rotation, and the
ML-DSA migration path — and reports the states where signing
continuity breaks.

**Canonical results page: `docs/index.html`.**

## Pinned tree

- Repository: postfiatd
- Commit: `0085a1ff885d6a446369cf73a4430f75af22be55`
  ("Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9")
- A local checkout of that commit was used for the code reading. The
  tree must be the `0085a1ff` tree, not any branch head: the worktree
  used at authoring time was a detached checkout at `0085a1ff`
  (`~/workspace/postfiatd-amendment/worktree-0085a1ff`). The harness
  records the tree's `HEAD` commit in
  `results/simulation_summary.json`, so a wrong tree is detectable.
- Upstream comparison: postfiatd's amendment-vote logic (`doVoting`)
  is byte-identical to upstream rippled 2.5.0; the only divergence is
  the amendment-majority threshold, 67/100 in postfiatd vs 80/100
  upstream (`include/xrpl/protocol/SystemParameters.h:85`). Source:
  the amendment-vote research notes
  (`~/workspace/postfiatd-amendment/RESEARCH.md`).

## Headline numbers (from `results/simulation_summary.json`)

Validator set modelled: **N=66** (the count listed by the PostFiat
testnet explorer on 2026-11-13, ledger ~8,016,789). Seed 20261113,
56 simulated days.

- Validation quorum (67% rule): **45** of 66; amendment minimum
  votes: **45**. Upstream 80% rule: quorum **53**, amendment minimum
  **53**.
- Compromise: quorum breaks at **22** compromised validators (67%
  rule) and at **14** (80% rule); **21** / **13** compromised are
  still tolerated.
- Staggered rotation (weekly batches of 9, 7-day overlap, 0-day
  propagation delay): **0** validators without a trusted key on any
  day; quorum met every day under both rules. Stress variant (2-day
  delay, no overlap): worst day **9** validators without a trusted
  key; quorum still met under both rules.
- Mid-rotation failure (one validator, new manifest never trusted,
  recovery after 7 days): **7** days without a trusted key; quorum
  intact (margins 20 at 67%, 12 at 80%). Fleet variant: quorum breaks
  at **22** simultaneous failures (67%) / **14** (80%).
- Mixed network: old nodes lose quorum once **22** validators are
  hybrid-only (67%) / **14** (80%). Dual-signed validators do not
  shrink the old nodes' verifiable set.
- Coordinated whole-set rotation: quorum lost for
  `max(0, propagation_delay - overlap)` days — no loss at 0-day
  delay; 7 days lost at delay 7 / overlap 0.

## Reproduce

Requirements: Python 3.8+ (standard library only), a checkout of the
pinned tree, `git` (only to record the tree commit), `sha256sum`.

```sh
# 1. Run the harness (baseline + stress variant) and rebuild the results page:
./run_all.sh

# 2. Verify the digest manifest:
./verify_digests.sh --check
```

`run_all.sh` runs `rotation_sim.py` (writes `results/*.json`,
`results/*.csv`, `results/summary.txt`, plus the
`results/stress/` variant), then `build_results.py` (writes
`docs/index.html` from the summary JSON), then `verify_digests.sh`
(rebuilds `SHA256SUMS`). No network access is used at any step. The
harness output is deterministic: two runs over the same tree produce
byte-identical outputs (seeded PRNG, fixed simulated calendar, no
timestamps written into outputs). See `REPRODUCTION.md` for the
fresh-environment reproduction record.

The tree to check defaults to the pinned worktree used at authoring
time; override with `POSTFIATD_TREE=/path/to/postfiatd-tree`. If the
tree is absent or its HEAD differs from the pinned commit, the harness
still runs but records `tree_matches_pinned_commit: false` in the
summary JSON — the simulation does not depend on the tree, only the
code citations do.

## Files

- `rotation_sim.py` — the harness (Python 3, standard library only)
- `build_results.py` — builds `docs/index.html` from the summary JSON
- `results/simulation_summary.json` — every scenario result, config,
  assumptions
- `results/threshold_table.csv` — quorum / amendment votes / break
  points for N = 16, 25, 53, 66 at 67% and 80%
- `results/rotation_schedule.csv` — per-day validator-set state,
  staggered rotation (baseline)
- `results/stress/` — same outputs for the 2-day-delay / no-overlap
  variant
- `results/compromise_sweep.csv` — quorum reachability vs compromised
  count, k = 0..66
- `results/mixed_network.csv` — old-node quorum vs hybrid-only count
- `results/coordinated_rotation.csv` — quorum loss vs propagation
  delay / overlap grid
- `results/summary.txt` — human-readable summary
- `docs/index.html` — canonical results page
- `key_lifecycle.md` — generation, custody, rotation procedure,
  ML-DSA migration path
- `compromise_runbook.md` — detection, containment, recovery for a
  suspected key compromise, with worked examples
- `assumptions.md` — verified-vs-assumed register and open questions
- `sources.md` — primary sources for every standard-derived claim

## Limits (read before relying on any number here)

- This is a **model** of the mechanics in the pinned source tree,
  not a measurement of the live network. The ledger was not compiled
  or run (a full build is not feasible on the audit machine: no
  Conan, ~1 GB RAM available).
- The pinned code has **no dual-signing state**: a manifest carries
  exactly one signing key. The "overlap window" is an operational
  procedure (publish the manifest early, activate late), not a
  protocol feature.
- The validator-set size (N=66) is a snapshot from 2026-11-13, not a
  protocol constant. Re-check the explorer before planning a rotation.
- Everything assumed rather than verified is listed in
  `assumptions.md`, with the open questions the pack does not settle.
