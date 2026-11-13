#!/usr/bin/env python3
"""Validator key rotation / compromise simulation for the postfiatd ledger.

Models validator-set mechanics derived from the pinned postfiatd tree
(commit 0085a1ff885d6a446369cf73a4430f75af22be55). This is a MODEL of the
mechanics in that source tree, not a simulation of the live network and
not a run of the ledger: no ledger code is compiled or executed here.

Mechanics taken from the pinned tree (see README.md and assumptions.md
for the file:line citations and for what is assumed rather than verified):

* Validation quorum: ceil(max(0.67 * effective_UNL, 0.60 * UNL))
  (src/xrpld/app/misc/detail/ValidatorList.cpp, calculateQuorum).
  Upstream XRPL uses 0.80; this tree uses 0.67 for devnet/testnet.
* Amendment majority (post-fix): votes > floor(N * 67 / 100), with a
  2-week majority hold before an amendment enables
  (include/xrpl/protocol/SystemParameters.h:85,
  src/xrpld/app/misc/detail/AmendmentTable.cpp, computeThreshold /
  passes / doVoting).
* Validator identity is a master key; validations are signed by an
  ephemeral signing key bound to the master key by a manifest carrying
  a sequence number. A higher-sequence manifest supersedes the old
  signing key; sequence 0xFFFFFFFF revokes the master key entirely
  (src/xrpld/app/misc/Manifest.h, header comment).
* Manifests propagate by peer gossip and via validator-list sites; the
  site fetcher refreshes every 5 minutes by default
  (src/xrpld/app/misc/detail/ValidatorSite.cpp).

Determinism: all randomness comes from one seeded PRNG (default seed
20261113, recorded in the output). The simulated calendar starts on a
fixed date (2026-11-13). No wall-clock time, no network access, no
timestamps are written into the outputs.

Usage:
    python3 rotation_sim.py [--validators N] [--seed S]
                            [--horizon-days D] [--overlap-days W]
                            [--propagation-delay-days P]
                            [--recovery-days R]
                            [--out-dir DIR] [--tree DIR]

Outputs (into --out-dir, default ./results):
    simulation_summary.json   every scenario result + config + assumptions
    threshold_table.csv       quorum / amendment votes / break points
    rotation_schedule.csv     per-day validator-set state, staggered rotation
    compromise_sweep.csv      quorum reachability vs compromised count
    mixed_network.csv         old-node quorum vs hybrid-only validator count
    coordinated_rotation.csv  quorum loss vs propagation delay / lead time
    summary.txt               human-readable summary of the same results
"""

import argparse
import csv
import json
import math
import os
import random
import subprocess
import sys
from datetime import date, timedelta

VERSION = "1.0.0"
PINNED_COMMIT = "0085a1ff885d6a446369cf73a4430f75af22be55"
DEFAULT_TREE = "/home/hatch/workspace/postfiatd-amendment/worktree-0085a1ff"
SIM_START = date(2026, 11, 13)

# postfiatd (this tree) vs upstream rippled majority fractions.
POSTFIATD_NUM, POSTFIATD_DEN = 67, 100
UPSTREAM_NUM, UPSTREAM_DEN = 80, 100
# Absolute-minimum-quorum floor from the negative-UNL protocol:
# 60% of the original UNL size.
ABS_MIN_NUM, ABS_MIN_DEN = 60, 100

# Validator-set sizes modelled. 66 is the default: the number of
# validators listed by the PostFiat testnet explorer on 2026-11-13.
# 25 is the explorer's reported "UNL Count" on the same day (its exact
# meaning is unverified; it is modelled as a sensitivity case, not as
# a confirmed UNL size). 53 is the testnet size recorded earlier in
# 2026 (now superseded by the live 66). 16 matches the AmendmentTable
# test fixtures.
TABLE_SIZES = [16, 25, 53, 66]


def ceil_div(a, b):
    return -(-a // b)


def amendment_min_votes(n, num, den):
    """Minimum yes-votes for an amendment majority, post-fix rule.

    threshold = floor(N * num / den); passes() requires votes > threshold.
    """
    return (n * num) // den + 1


def validation_quorum(n, num, den):
    """Validations needed for a ledger to close.

    max(ceil(N * num / den), ceil(N * 60 / 100)) — the 60% term is the
    absolute-minimum-quorum floor from the negative-UNL protocol.
    """
    return max(ceil_div(n * num, den), ceil_div(n * ABS_MIN_NUM, ABS_MIN_DEN))


def threshold_table():
    rows = []
    for n in TABLE_SIZES:
        for label, num, den in (("postfiatd-67pct", POSTFIATD_NUM, POSTFIATD_DEN),
                                ("upstream-80pct", UPSTREAM_NUM, UPSTREAM_DEN)):
            q = validation_quorum(n, num, den)
            m = amendment_min_votes(n, num, den)
            rows.append({
                "validators_n": n,
                "rule": label,
                "validation_quorum": q,
                "amendment_min_votes": m,
                # Compromised / offline validators the set still tolerates
                # while reaching quorum: N - quorum.
                "max_offline_tolerated": n - q,
                # Smallest compromised/offline count that breaks quorum.
                "break_at_offline": n - q + 1,
                # Byzantine bound from the quorum comment (Theorem 8,
                # arXiv:1802.07242): t <= (1 - quorum_fraction) * N.
                "max_byzantine_tolerated": n - q,
            })
    return rows


def rotation_schedule(n, seed, horizon_days, overlap_days,
                      propagation_delay_days):
    """Staggered rotation: the set rotates in weekly batches over the horizon.

    Each validator rotates once. Its new manifest is published
    `overlap_days` before its activation day (the day the validator
    restarts with the new token and starts signing with the new key);
    it takes `propagation_delay_days` for the new manifest to be
    trusted network-wide. The old signing key stops being accepted
    once peers see the higher-sequence manifest, so the validator has
    no network-wide trusted signing key for
    max(0, propagation_delay_days - overlap_days) days.

    The pinned code has no dual-signing state — a manifest carries
    exactly one signing key — so the overlap is achieved operationally
    by publishing the manifest early and activating late, not by a
    protocol feature. See assumptions.md.
    """
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    weeks = max(1, horizon_days // 7)
    batch = ceil_div(n, weeks)
    # activation day per validator: weekly batches, shuffled order.
    activation = {}
    for pos, v in enumerate(order):
        activation[v] = (pos // batch) * 7
    gap = max(0, propagation_delay_days - overlap_days)
    rows = []
    for day in range(horizon_days):
        in_transition = 0
        offline = 0
        for v in range(n):
            act = activation[v]
            if act <= day < act + gap:
                # New key not yet trusted network-wide, old key already
                # superseded: no trusted signing key.
                in_transition += 1
                offline += 1
        signing = n - offline
        q67 = validation_quorum(n, POSTFIATD_NUM, POSTFIATD_DEN)
        q80 = validation_quorum(n, UPSTREAM_NUM, UPSTREAM_DEN)
        rows.append({
            "day": day,
            "date": (SIM_START + timedelta(days=day)).isoformat(),
            "rotations_today": sum(1 for v in range(n) if activation[v] == day),
            "validators_in_transition": in_transition,
            "validators_without_trusted_key": offline,
            "signing_validators": signing,
            "validation_quorum_67pct": q67,
            "quorum_met_67pct": signing >= q67,
            "validation_quorum_80pct": q80,
            "quorum_met_80pct": signing >= q80,
        })
    breach_67 = [r["day"] for r in rows if not r["quorum_met_67pct"]]
    breach_80 = [r["day"] for r in rows if not r["quorum_met_80pct"]]
    return rows, {
        "validators_n": n,
        "horizon_days": horizon_days,
        "weekly_batch_size": batch,
        "overlap_days_planned": overlap_days,
        "propagation_delay_days": propagation_delay_days,
        "transition_gap_days": gap,
        "max_validators_without_trusted_key": max(r["validators_without_trusted_key"] for r in rows),
        "quorum_breach_days_67pct": breach_67,
        "quorum_breach_days_80pct": breach_80,
        "quorum_met_every_day_67pct": not breach_67,
        "quorum_met_every_day_80pct": not breach_80,
    }


def rotation_failure(n, seed, horizon_days, recovery_days):
    """Mid-rotation failure: a validator's new manifest never propagates.

    The validator restarts with the new token (so it signs only with
    the new key, which no peer trusts) while the old key is superseded.
    It has no trusted signing key from its activation day until the
    operator republishes a working manifest `recovery_days` later.
    The fleet variant asks how many validators must fail at once to
    break quorum.
    """
    rng = random.Random(seed + 1)
    victim = rng.randrange(n)
    act_day = 7  # failure in the second week of the schedule
    offline_days = []
    for day in range(horizon_days):
        if act_day <= day < act_day + recovery_days:
            offline_days.append(day)
    q67 = validation_quorum(n, POSTFIATD_NUM, POSTFIATD_DEN)
    q80 = validation_quorum(n, UPSTREAM_NUM, UPSTREAM_DEN)
    single = {
        "failed_validator_index": victim,
        "activation_day": act_day,
        "recovery_days": recovery_days,
        "days_without_trusted_key": len(offline_days),
        "offline_day_range": [offline_days[0], offline_days[-1]] if offline_days else [],
        "signing_validators_during_outage": n - 1,
        "quorum_met_67pct_during_outage": (n - 1) >= q67,
        "quorum_met_80pct_during_outage": (n - 1) >= q80,
        "quorum_margin_67pct": (n - 1) - q67,
        "quorum_margin_80pct": (n - 1) - q80,
    }
    # Fleet variant: f validators fail simultaneously, same recovery.
    fleet_break_67 = None
    fleet_break_80 = None
    for f in range(0, n + 1):
        if fleet_break_67 is None and (n - f) < q67:
            fleet_break_67 = f
        if fleet_break_80 is None and (n - f) < q80:
            fleet_break_80 = f
    fleet = {
        "max_simultaneous_failures_tolerated_67pct": (n - q67),
        "breaks_quorum_at_failures_67pct": fleet_break_67,
        "max_simultaneous_failures_tolerated_80pct": (n - q80),
        "breaks_quorum_at_failures_80pct": fleet_break_80,
    }
    return single, fleet


def compromise_sweep(n):
    """k validators compromised: their votes are lost (revoked / offline).

    Two readings share the same arithmetic: (a) compromised keys are
    revoked, so those validators stop voting; (b) compromised keys
    vote adversarially, so only the N - k honest votes can ever count
    toward quorum. Either way quorum is reachable iff N - k >= quorum.
    """
    rows = []
    q67 = validation_quorum(n, POSTFIATD_NUM, POSTFIATD_DEN)
    q80 = validation_quorum(n, UPSTREAM_NUM, UPSTREAM_DEN)
    m67 = amendment_min_votes(n, POSTFIATD_NUM, POSTFIATD_DEN)
    m80 = amendment_min_votes(n, UPSTREAM_NUM, UPSTREAM_DEN)
    for k in range(0, n + 1):
        honest = n - k
        rows.append({
            "compromised_validators_k": k,
            "honest_validators": honest,
            "validation_quorum_67pct": q67,
            "quorum_reachable_67pct": honest >= q67,
            "validation_quorum_80pct": q80,
            "quorum_reachable_80pct": honest >= q80,
            "amendment_min_votes_67pct": m67,
            "amendment_reachable_67pct": honest >= m67,
            "amendment_min_votes_80pct": m80,
            "amendment_reachable_80pct": honest >= m80,
        })
    return rows, {
        "validators_n": n,
        "break_at_compromised_67pct": n - q67 + 1,
        "break_at_compromised_80pct": n - q80 + 1,
        "max_compromised_tolerated_67pct": n - q67,
        "max_compromised_tolerated_80pct": n - q80,
        "byzantine_bound_note": (
            "With a 67% quorum the fork-safety bound in the quorum comment "
            "allows t <= 0.33*N Byzantine validators; liveness (quorum) "
            "breaks at the same k as the table's break point."),
    }


def mixed_network(n):
    """Mixed classical / post-quantum network: hybrid-only validators.

    During migration some validators carry ML-DSA-only signing keys.
    Old nodes verify only the classical half of a hybrid signature, so
    a validator that presents no classical signature is unverifiable
    to them. If h validators are hybrid-only, an old node's effective
    signing set is N - h while its quorum is still computed over its
    full UNL of N. Old nodes keep quorum iff N - h >= quorum.
    Validators that dual-sign (classical + ML-DSA) count for both.
    """
    rows = []
    q67 = validation_quorum(n, POSTFIATD_NUM, POSTFIATD_DEN)
    q80 = validation_quorum(n, UPSTREAM_NUM, UPSTREAM_DEN)
    for h in range(0, n + 1):
        eff = n - h
        rows.append({
            "hybrid_only_validators_h": h,
            "hybrid_only_pct": round(100.0 * h / n, 2),
            "verifiable_by_old_nodes": eff,
            "validation_quorum_67pct": q67,
            "old_nodes_reach_quorum_67pct": eff >= q67,
            "validation_quorum_80pct": q80,
            "old_nodes_reach_quorum_80pct": eff >= q80,
        })
    return rows, {
        "validators_n": n,
        "max_hybrid_only_tolerated_67pct": n - q67,
        "old_nodes_lose_quorum_at_hybrid_only_67pct": n - q67 + 1,
        "max_hybrid_only_tolerated_80pct": n - q80,
        "old_nodes_lose_quorum_at_hybrid_only_80pct": n - q80 + 1,
        "note": ("Dual-signed (hybrid) validators count for old and new "
                 "nodes alike; only hybrid-ONLY validators shrink the "
                 "old nodes' verifiable set."),
    }


def coordinated_rotation(n, horizon_days):
    """Whole-set rotation on one day, over a grid of delay / overlap values.

    If every validator rotates on the same day and manifest propagation
    takes D days while the operator publishes the new manifests O days
    before activating them, the whole set has no network-wide trusted
    key for max(0, D - O) days and quorum is lost for exactly those
    days (conservative counting: a validator in transition counts as
    not signing).
    """
    rows = []
    for delay in (0, 1, 2, 7):
        for overlap in (0, 1, 7):
            gap = max(0, delay - overlap)
            rows.append({
                "propagation_delay_days": delay,
                "overlap_days": overlap,
                "days_without_quorum": gap,
                "quorum_lost": gap > 0,
            })
    return rows, {
        "validators_n": n,
        "note": ("With delay 0 (minutes-scale propagation, consistent "
                 "with the 5-minute validator-site refresh) there is no "
                 "quorum loss even for a same-day whole-set rotation. "
                 "Loss appears only when propagation delay exceeds the "
                 "overlap (pre-publication) window."),
    }


def check_tree(tree_dir):
    """Return the HEAD commit of the tree, or None if unavailable."""
    if not tree_dir or not os.path.isdir(tree_dir):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", tree_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=30)
        return out.stdout.strip()
    except Exception:
        return None


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validators", type=int, default=66)
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--horizon-days", type=int, default=56)
    ap.add_argument("--overlap-days", type=int, default=7)
    ap.add_argument("--propagation-delay-days", type=int, default=0)
    ap.add_argument("--recovery-days", type=int, default=7)
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--tree", default=os.environ.get("POSTFIATD_TREE", DEFAULT_TREE))
    args = ap.parse_args(argv)

    n = args.validators
    out = args.out_dir
    os.makedirs(out, exist_ok=True)

    tree_commit = check_tree(args.tree)
    tree_verified = tree_commit == PINNED_COMMIT

    table = threshold_table()
    sched_rows, sched_sum = rotation_schedule(
        n, args.seed, args.horizon_days, args.overlap_days,
        args.propagation_delay_days)
    fail_single, fail_fleet = rotation_failure(
        n, args.seed, args.horizon_days, args.recovery_days)
    comp_rows, comp_sum = compromise_sweep(n)
    mix_rows, mix_sum = mixed_network(n)
    coord_rows, coord_sum = coordinated_rotation(n, args.horizon_days)

    summary = {
        "harness": "rotation_sim.py",
        "harness_version": VERSION,
        "pinned_commit": PINNED_COMMIT,
        "tree_checked": args.tree,
        "tree_head_commit": tree_commit,
        "tree_matches_pinned_commit": tree_verified,
        "config": {
            "validators_n": n,
            "seed": args.seed,
            "horizon_days": args.horizon_days,
            "sim_start_date": SIM_START.isoformat(),
            "overlap_days_planned": args.overlap_days,
            "propagation_delay_days": args.propagation_delay_days,
            "recovery_days": args.recovery_days,
        },
        "thresholds": {
            "postfiatd_validation_quorum": validation_quorum(n, POSTFIATD_NUM, POSTFIATD_DEN),
            "postfiatd_amendment_min_votes": amendment_min_votes(n, POSTFIATD_NUM, POSTFIATD_DEN),
            "upstream_validation_quorum": validation_quorum(n, UPSTREAM_NUM, UPSTREAM_DEN),
            "upstream_amendment_min_votes": amendment_min_votes(n, UPSTREAM_NUM, UPSTREAM_DEN),
            "note": ("postfiatd uses 67/100 for both the validation quorum "
                     "and the amendment majority; upstream rippled uses "
                     "80/100 for both."),
        },
        "threshold_table": table,
        "rotation_schedule": sched_sum,
        "rotation_failure_single": fail_single,
        "rotation_failure_fleet": fail_fleet,
        "compromise": comp_sum,
        "mixed_network": mix_sum,
        "coordinated_rotation": coord_sum,
        "assumptions": [
            "Validator-set size N=66 is the number of validators listed by "
            "the PostFiat testnet explorer on 2026-11-13 (ledger ~8,016,789); "
            "it is a snapshot, not a protocol constant, and the set changes "
            "as validators join and leave.",
            "The model counts a validator as signing only when it has a "
            "network-wide trusted signing key. A validator in manifest "
            "transition (new manifest published, not yet trusted by all "
            "peers) counts as NOT signing — a conservative choice.",
            "The pinned code has no dual-signing state: a manifest carries "
            "exactly one signing key. The 'overlap window' in the schedule "
            "is an operational procedure (publish the new manifest early, "
            "activate late), not a protocol feature; see assumptions.md.",
            "UNL update propagation is modelled as a single delay in whole "
            "days. The code's validator-site refresh is 5 minutes by "
            "default, so the baseline delay of 0 days (minutes-scale) is "
            "the realistic case; multi-day delays are stress cases.",
            "Compromised validators are modelled as losing their votes "
            "entirely (revoked or voting adversarially). The model does "
            "not simulate double-signing, equivocation detection, or "
            "negative-UNL exclusion dynamics.",
            "Amendment votes expire 24 hours after a validator's last "
            "validation; the model does not simulate vote expiry, because "
            "the modelled outages are counted in whole days and any "
            "validator offline for a full day has no live vote anyway.",
        ],
    }

    write_csv(os.path.join(out, "threshold_table.csv"),
              list(table[0].keys()), table)
    write_csv(os.path.join(out, "rotation_schedule.csv"),
              list(sched_rows[0].keys()), sched_rows)
    write_csv(os.path.join(out, "compromise_sweep.csv"),
              list(comp_rows[0].keys()), comp_rows)
    write_csv(os.path.join(out, "mixed_network.csv"),
              list(mix_rows[0].keys()), mix_rows)
    write_csv(os.path.join(out, "coordinated_rotation.csv"),
              list(coord_rows[0].keys()), coord_rows)
    with open(os.path.join(out, "simulation_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    txt = []
    t = summary["thresholds"]
    txt.append("Validator key rotation / compromise simulation")
    txt.append("postfiatd commit %s" % PINNED_COMMIT)
    txt.append("Validators modelled: N=%d (seed %d, %d simulated days from %s)"
               % (n, args.seed, args.horizon_days, SIM_START.isoformat()))
    txt.append("Tree HEAD matches pinned commit: %s" % tree_verified)
    txt.append("")
    txt.append("Thresholds (N=%d): validation quorum 67%% = %d, amendment min votes 67%% = %d; "
               "upstream 80%%: quorum %d, amendment min votes %d."
               % (n, t["postfiatd_validation_quorum"],
                  t["postfiatd_amendment_min_votes"],
                  t["upstream_validation_quorum"],
                  t["upstream_amendment_min_votes"]))
    txt.append("")
    txt.append("Compromise: quorum breaks at %d compromised validators (67%% rule) "
               "and at %d (80%% rule); %d / %d compromised are still tolerated."
               % (comp_sum["break_at_compromised_67pct"],
                  comp_sum["break_at_compromised_80pct"],
                  comp_sum["max_compromised_tolerated_67pct"],
                  comp_sum["max_compromised_tolerated_80pct"]))
    txt.append("")
    txt.append("Staggered rotation (%d validators over %d days, propagation delay %d days, "
               "overlap window %d days): max validators without a trusted key on any "
               "day = %d; quorum met every day under the 67%% rule: %s; under the 80%% rule: %s."
               % (n, args.horizon_days, args.propagation_delay_days,
                  args.overlap_days,
                  sched_sum["max_validators_without_trusted_key"],
                  sched_sum["quorum_met_every_day_67pct"],
                  sched_sum["quorum_met_every_day_80pct"]))
    txt.append("")
    txt.append("Mid-rotation failure (one validator, new manifest never trusted, recovery "
               "after %d days): %d days without a trusted key; quorum still met under both "
               "rules (margins %d at 67%%, %d at 80%%). Fleet variant: quorum breaks when "
               "%d validators fail at once (67%%) or %d (80%%)."
               % (args.recovery_days, fail_single["days_without_trusted_key"],
                  fail_single["quorum_margin_67pct"],
                  fail_single["quorum_margin_80pct"],
                  fail_fleet["breaks_quorum_at_failures_67pct"],
                  fail_fleet["breaks_quorum_at_failures_80pct"]))
    txt.append("")
    txt.append("Mixed network: old nodes lose quorum once %d validators are hybrid-only "
               "(67%% rule) or %d (80%% rule). Dual-signed validators do not shrink the "
               "old nodes' verifiable set."
               % (mix_sum["old_nodes_lose_quorum_at_hybrid_only_67pct"],
                  mix_sum["old_nodes_lose_quorum_at_hybrid_only_80pct"]))
    txt.append("")
    txt.append("Coordinated whole-set rotation: no quorum loss when propagation delay is "
               "0 days; loss lasts max(0, delay - overlap) days otherwise — see "
               "coordinated_rotation.csv.")
    txt.append("")
    txt.append("This is a model of the mechanics in the pinned source tree, not a "
               "measurement of the live network. Assumptions are listed in "
               "simulation_summary.json and assumptions.md.")
    with open(os.path.join(out, "summary.txt"), "w") as f:
        f.write("\n".join(txt) + "\n")

    print("rotation_sim.py %s: N=%d seed=%d horizon=%d days" % (VERSION, n, args.seed, args.horizon_days))
    print("  quorum 67%%=%d amendment-min-votes 67%%=%d | quorum 80%%=%d amendment-min-votes 80%%=%d"
          % (t["postfiatd_validation_quorum"], t["postfiatd_amendment_min_votes"],
             t["upstream_validation_quorum"], t["upstream_amendment_min_votes"]))
    print("  compromise breaks quorum at k=%d (67%%) / k=%d (80%%)"
          % (comp_sum["break_at_compromised_67pct"], comp_sum["break_at_compromised_80pct"]))
    print("  rotation: max without trusted key=%d, quorum every day 67%%=%s 80%%=%s"
          % (sched_sum["max_validators_without_trusted_key"],
             sched_sum["quorum_met_every_day_67pct"],
             sched_sum["quorum_met_every_day_80pct"]))
    print("  outputs written to %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
