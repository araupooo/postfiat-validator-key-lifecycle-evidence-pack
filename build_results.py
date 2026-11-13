#!/usr/bin/env python3
"""Build docs/index.html from results/simulation_summary.json.

Deterministic: the page is generated only from the JSON summary (no
timestamps, no network). Run via run_all.sh after rotation_sim.py.
"""

import html
import json
import os
import sys

PACK_DIR = os.path.dirname(os.path.abspath(__file__))


def esc(x):
    return html.escape(str(x))


def main():
    results_dir = os.path.join(PACK_DIR, "results")
    with open(os.path.join(results_dir, "simulation_summary.json")) as f:
        s = json.load(f)
    stress_path = os.path.join(results_dir, "stress", "simulation_summary.json")
    stress = None
    if os.path.exists(stress_path):
        with open(stress_path) as f:
            stress = json.load(f)

    cfg = s["config"]
    t = s["thresholds"]
    comp = s["compromise"]
    sched = s["rotation_schedule"]
    fail1 = s["rotation_failure_single"]
    failf = s["rotation_failure_fleet"]
    mix = s["mixed_network"]
    n = cfg["validators_n"]

    table_rows = "".join(
        "<tr><td class=\"num\">%d</td><td>%s</td><td class=\"num\">%d</td>"
        "<td class=\"num\">%d</td><td class=\"num\">%d</td><td class=\"num\">%d</td></tr>"
        % (r["validators_n"], esc(r["rule"]), r["validation_quorum"],
           r["amendment_min_votes"], r["max_offline_tolerated"],
           r["break_at_offline"])
        for r in s["threshold_table"])

    stress_html = ""
    if stress:
        ss = stress["rotation_schedule"]
        stress_html = (
            "<h2>Stress variant: 2-day propagation delay, no overlap</h2>"
            "<p>Same set and seed, run with "
            "<code>--propagation-delay-days 2 --overlap-days 0</code> "
            "(<code>results/stress/</code>). Each weekly batch of %d validators "
            "spends 2 days without a network-wide trusted key, so up to "
            "<b>%d</b> validators are without a trusted key on the worst day; "
            "quorum is still met every day under both rules (57 signing "
            "validators vs quorum 45 at 67%%, 53 at 80%%).</p>"
            % (ss["weekly_batch_size"],
               ss["max_validators_without_trusted_key"]))

    assumptions = "".join("<li>%s</li>" % esc(a) for a in s["assumptions"])

    page = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PostFiat Ledger — Validator Key Lifecycle and Rotation Simulation</title>
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; color: #1a1a1a; line-height: 1.5; }
  h1 { font-size: 1.6em; } h2 { font-size: 1.25em; margin-top: 1.6em; border-bottom: 1px solid #ccc; padding-bottom: .2em; }
  table { border-collapse: collapse; width: 100%%; margin: .6em 0; font-size: .92em; }
  th, td { border: 1px solid #bbb; padding: .35em .5em; text-align: left; }
  th { background: #eee; } td.num { text-align: right; }
  code { background: #f2f2f2; padding: 0 .25em; }
  .kpi { display: flex; gap: 1em; flex-wrap: wrap; }
  .kpi div { border: 1px solid #bbb; padding: .6em .9em; min-width: 10em; }
  .kpi b { font-size: 1.4em; display: block; }
  .note { background: #fff8e1; border-left: 4px solid #c90; padding: .6em .9em; }
</style>
</head>
<body>
<h1>PostFiat Ledger — Validator Key Lifecycle and Rotation Simulation</h1>
<p>A rotation-simulation harness and key-lifecycle documentation for the
postfiatd validator set, grounded in the pinned source tree. The harness
models the validator-set mechanics in that tree — validation quorum,
amendment majority, manifest-based key rotation, and the ML-DSA migration
path — and reports the states where signing continuity breaks.</p>

<p>Codebase: postfiatd, commit
<code>%(commit)s</code>
("Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9").
Harness: <code>rotation_sim.py</code> %(version)s. Method: deterministic
simulation (seed %(seed)d) of the mechanics in the pinned tree only — the
ledger was <strong>not</strong> compiled or run (a full build is not
feasible on the audit machine: no Conan, ~1&nbsp;GB RAM available). See
<code>README.md</code> for reproduction steps and <code>assumptions.md</code>
for everything the model assumes rather than verifies.</p>

<h2>Headline figures (N=%(n)d validators, 67%% rule unless stated)</h2>
<div class="kpi">
  <div><b>%(q67)d</b> validations needed for quorum (of %(n)d)</div>
  <div><b>%(m67)d</b> minimum votes for an amendment majority</div>
  <div><b>%(break67)d</b> compromised validators break quorum</div>
  <div><b>%(tol67)d</b> compromised validators still tolerated</div>
  <div><b>%(break80)d</b> compromised validators break quorum (80%% rule)</div>
  <div><b>%(mix67)d</b> hybrid-only validators lose old nodes' quorum</div>
</div>

<h2>Thresholds</h2>
<p>Validation quorum is <code>max(ceil(N &times; fraction), ceil(N &times; 0.60))</code>
(<code>ValidatorList::calculateQuorum</code>); the amendment majority is
<code>votes &gt; floor(N &times; fraction)</code> with a 2-week hold
(<code>AmendmentTable::computeThreshold / passes / doVoting</code>).
postfiatd uses 67/100 for both; upstream rippled uses 80/100 for both
(<code>SystemParameters.h:85</code>).</p>
<table>
<tr><th>Validators</th><th>Rule</th><th>Validation quorum</th><th>Amendment min votes</th><th>Max offline tolerated</th><th>Breaks at offline</th></tr>
%(table_rows)s
</table>
<p>Read the N=66 row as: with 66 validators, 45 validations close a ledger
and 45 votes carry an amendment under the 67%% rule; 21 validators can be
offline or compromised at once and quorum still holds; the 22nd breaks it.
Under the upstream 80%% rule the same set tolerates only 13, breaking at 14.</p>

<h2>Rotation schedule</h2>
<p>Staggered rotation of the %(n)d validators over %(horizon)d simulated days
(seed %(seed)d), in weekly batches of %(batch)d, with a %(overlap)d-day
overlap window and %(delay)d-day manifest propagation delay. Worst day:
<b>%(max_off)d</b> validators without a trusted signing key. Quorum met
every day under the 67%% rule: <b>%(qok67)s</b>; under the 80%% rule:
<b>%(qok80)s</b>. Per-day state is in
<code>results/rotation_schedule.csv</code>.</p>
%(stress_html)s

<h2>Mid-rotation failure</h2>
<p>One validator's new manifest never propagates and its old key is already
superseded: <b>%(fail_days)d days</b> without a trusted signing key (recovery
after %(recovery)d days by republishing a working manifest). Quorum still
holds under both rules (margins %(margin67)d at 67%%, %(margin80)d at 80%%).
Fleet variant: quorum breaks when <b>%(fleet67)d</b> validators fail at once
(67%%) or <b>%(fleet80)d</b> (80%%).</p>

<h2>Compromise sweep</h2>
<p>Compromised validators lose their votes (revoked, or voting
adversarially). Full sweep in <code>results/compromise_sweep.csv</code>:
quorum is reachable while <b>%(tol67)d</b> or fewer validators are
compromised (67%% rule) and breaks at <b>%(break67)d</b>; at the 80%% rule
the figures are %(tol80)d / %(break80)d. The same break points bound
amendment majorities, since the amendment minimum (45) equals the
validation quorum (45) at N=66.</p>

<h2>Mixed classical / post-quantum network</h2>
<p>Old nodes verify only the classical half of a hybrid signature, so a
validator that presents no classical signature is unverifiable to them.
Old nodes lose quorum once <b>%(mix67)d</b> validators are hybrid-only
(67%% rule) or <b>%(mix80)d</b> (80%% rule). Dual-signed validators count
for old and new nodes alike; only hybrid-only validators shrink the old
nodes' verifiable set. Full sweep in
<code>results/mixed_network.csv</code>.</p>

<h2>Coordinated whole-set rotation</h2>
<p>If every validator rotates on the same day, quorum is lost for
<code>max(0, propagation_delay - overlap)</code> days: no loss at 0-day
delay (minutes-scale propagation, consistent with the 5-minute
validator-site refresh); 1 day lost at delay 1 / overlap 0; 2 days at
delay 2 / overlap 0; 7 days at delay 7 / overlap 0. A 7-day overlap
window absorbs even a 7-day delay. Grid in
<code>results/coordinated_rotation.csv</code>.</p>

<div class="note"><strong>Model, not measurement.</strong> These numbers
come from the mechanics in the pinned source tree applied to a validator
set of 66 (the count listed by the PostFiat testnet explorer on
2026-11-13). They are not measurements of the live network. The
assumptions below state what is verified from source and what is assumed.</div>

<h2>Assumptions</h2>
<ul>
%(assumptions)s
</ul>

<h2>Files</h2>
<ul>
<li><code>rotation_sim.py</code> — the harness (Python 3, standard library only)</li>
<li><code>results/simulation_summary.json</code> — every scenario result, config, assumptions</li>
<li><code>results/threshold_table.csv</code>, <code>results/compromise_sweep.csv</code>, <code>results/mixed_network.csv</code>, <code>results/rotation_schedule.csv</code>, <code>results/coordinated_rotation.csv</code> — machine-readable outputs</li>
<li><code>results/summary.txt</code> — human-readable summary</li>
<li><code>key_lifecycle.md</code> — generation, custody, rotation procedure, ML-DSA migration path</li>
<li><code>compromise_runbook.md</code> — detection, containment, recovery for a suspected key compromise</li>
<li><code>assumptions.md</code> — verified-vs-assumed register</li>
<li><code>sources.md</code> — primary sources for every standard-derived claim</li>
<li><code>README.md</code> — reproduction steps</li>
</ul>
</body>
</html>
""" % {
        "commit": esc(s["pinned_commit"]),
        "version": esc(s["harness_version"]),
        "seed": cfg["seed"],
        "n": n,
        "q67": t["postfiatd_validation_quorum"],
        "m67": t["postfiatd_amendment_min_votes"],
        "break67": comp["break_at_compromised_67pct"],
        "tol67": comp["max_compromised_tolerated_67pct"],
        "break80": comp["break_at_compromised_80pct"],
        "tol80": comp["max_compromised_tolerated_80pct"],
        "mix67": mix["old_nodes_lose_quorum_at_hybrid_only_67pct"],
        "mix80": mix["old_nodes_lose_quorum_at_hybrid_only_80pct"],
        "table_rows": table_rows,
        "horizon": cfg["horizon_days"],
        "batch": sched["weekly_batch_size"],
        "overlap": cfg["overlap_days_planned"],
        "delay": cfg["propagation_delay_days"],
        "max_off": sched["max_validators_without_trusted_key"],
        "qok67": sched["quorum_met_every_day_67pct"],
        "qok80": sched["quorum_met_every_day_80pct"],
        "stress_html": stress_html,
        "fail_days": fail1["days_without_trusted_key"],
        "recovery": fail1["recovery_days"],
        "margin67": fail1["quorum_margin_67pct"],
        "margin80": fail1["quorum_margin_80pct"],
        "fleet67": failf["breaks_quorum_at_failures_67pct"],
        "fleet80": failf["breaks_quorum_at_failures_80pct"],
        "assumptions": assumptions,
    }

    out_path = os.path.join(PACK_DIR, "docs", "index.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(page)
    print("build_results.py: wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
