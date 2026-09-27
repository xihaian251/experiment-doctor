"""Synthetic experiment for the Phase 4 audit-integration tests.

Deliberately prints a metric-looking line to stdout and writes a metric-shaped
CSV, so the tests can prove the captured adapter reads neither: stdout is a log,
and an unlabelled CSV column is not a metric of record.
"""

import argparse
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--exit", type=int, default=0)
args = parser.parse_args()

print(f"training with seed={args.seed}")
print("accuracy=99.0 loss=0.001")

out = pathlib.Path("results")
out.mkdir(exist_ok=True)
(out / "metrics.csv").write_text("epoch,accuracy\n1,0.99\n", encoding="utf-8")

sys.exit(args.exit)
