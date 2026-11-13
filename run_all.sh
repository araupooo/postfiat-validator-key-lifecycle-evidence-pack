#!/bin/sh
# Regenerate every derived output of this pack from scratch.
#   1. rotation_sim.py   -> results/*.json, results/*.csv, results/summary.txt
#                          (baseline + stress variant in results/stress/)
#   2. build_results.py  -> docs/index.html
#   3. verify_digests.sh -> SHA256SUMS (over every other pack file)
#
# The tree to check defaults to the pinned worktree used at authoring time;
# override with POSTFIATD_TREE=/path/to/postfiatd-tree.
# No network access is used at any step.
set -eu
PACK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TREE=${POSTFIATD_TREE:-/home/hatch/workspace/postfiatd-amendment/worktree-0085a1ff}

cd "$PACK_DIR"
python3 rotation_sim.py --tree "$TREE" --out-dir "$PACK_DIR/results"
python3 rotation_sim.py --tree "$TREE" --out-dir "$PACK_DIR/results/stress" \
    --propagation-delay-days 2 --overlap-days 0
python3 build_results.py
./verify_digests.sh
echo "run_all.sh: OK"
