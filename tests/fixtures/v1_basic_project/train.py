"""Synthetic "training" script for the v1 fixture project.

No ML framework: it reads config.yaml, prints a deterministic pseudo-loss curve
and writes results/metrics.csv.  Its only job is to exist, be launched, and
produce artifacts whose provenance can be locked and verified.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    seed = int(config.get("seed", 0))
    steps = int(config.get("steps", 5))
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    lines = ["step,loss"]
    value = float(seed)
    for step in range(steps):
        value = (value * 37 + 11) % 97 / 97
        lines.append(f"{step},{value:.4f}")
    (out / "metrics.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"trained seed={seed} steps={steps} -> {out / 'metrics.csv'}")


if __name__ == "__main__":
    main()
