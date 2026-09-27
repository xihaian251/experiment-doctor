"""Synthetic experiment for the Phase 5 full-pipeline golden.

Covers the whole chain: it accepts a seed, prints a metric-shaped line to stdout,
writes a metric-shaped CSV under results/, and exits with a caller-chosen code.
The stdout metric and the CSV exist so the golden can prove the audit path reads
neither -- stdout is a log and an unlabelled column is not a metric of record.
"""

import argparse
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--exit", type=int, default=0)
parser.add_argument("--epochs", type=int, default=1)
args = parser.parse_args()

print(f"training with seed={args.seed} epochs={args.epochs}")
print("accuracy=99.0 loss=0.001")

out = pathlib.Path("results")
out.mkdir(exist_ok=True)
rows = ["epoch,accuracy"] + [f"{e},0.99" for e in range(1, args.epochs + 1)]
(out / "metrics.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

sys.exit(args.exit)
