# Fresh-environment reproduction

## Procedure (2026-11-13)

1. Copied the pack to a clean directory:
   `cp -a <pack>/. /tmp/pack-repro-vkl/`
2. Ran the regeneration from scratch in that copy (no files carried
   over except the pack itself):
   `cd /tmp/pack-repro-vkl && ./run_all.sh`
   Exit code: **0**. Output tail: `run_all.sh: OK`.
3. Compared the regenerated derived outputs against the shipped ones
   with `cmp` (byte-for-byte) — all **IDENTICAL**:
   - `results/simulation_summary.json`
   - `results/threshold_table.csv`
   - `results/rotation_schedule.csv`
   - `results/compromise_sweep.csv`
   - `results/mixed_network.csv`
   - `results/coordinated_rotation.csv`
   - `results/summary.txt`
   - `results/stress/simulation_summary.json`
   - `results/stress/threshold_table.csv`
   - `results/stress/rotation_schedule.csv`
   - `results/stress/compromise_sweep.csv`
   - `results/stress/mixed_network.csv`
   - `results/stress/coordinated_rotation.csv`
   - `results/stress/summary.txt`
   - `docs/index.html`
4. Verified the regenerated digest manifest in the fresh copy:
   `./verify_digests.sh --check` — exit code **0**, all files OK.

## Result

**0 failures.** The harness output is deterministic: a fresh copy of
the pack regenerates byte-identical simulation results and results
page (seeded PRNG, fixed simulated calendar starting 2026-11-13, no
timestamps written into outputs).

## Notes

- The pinned tree itself is an input to the reproduction, not part of
  the pack: the fresh copy checked the same pinned worktree
  (`~/workspace/postfiatd-amendment/worktree-0085a1ff`, detached HEAD
  at `0085a1ff`) and recorded `tree_matches_pinned_commit: true` in
  both summary JSON files. A different tree commit would be recorded
  as a mismatch, not silently accepted.
- Environment at reproduction time: Python 3.12.3, git 2.43.0,
  GNU coreutils `sha256sum` (Ubuntu), same machine as authoring.
- The temporary copy at `/tmp/pack-repro-vkl/` is disposable; it was
  left in place for inspection and can be deleted.
