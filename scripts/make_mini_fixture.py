"""Build the miniature gmmvi fixture under tests/fixtures/mini_gmmvi.

Run once, by hand, if the fixture needs regenerating after a deliberate change:

    python scripts/make_mini_fixture.py

The fixture is a hand-shaped subset of the real Experiment 3 artifact layout: a repo
with fetch_exp3.py, cw2 configs and README prose, plus an extracted results tree whose
CSVs use the same header shape (pandas index column, then _step/num_samples/_runtime
and the metrics).  Values are round numbers so the expected aggregates are checkable by
hand in tests/test_gmmvi_small_fixture.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "mini_gmmvi"
REPO = ROOT / "repo"
RESULTS = ROOT / "extracted" / "evaluations" / "results"

FETCH = '''"""Miniature stand-in for the project's fetch script.

It keeps exactly the two constructs the adapter reads and nothing else: the
``fetch_exp3_eval`` declarations with their group lists and ``bad_run_ids``, and the
metric-direction rules inside the reported-value formatter.  It is never executed.
"""


def fetch_exp3_eval(project, foldername, group_names, metric="-elbo", secondary_metrics=[], bad_run_ids=[]):
    pass


def fetch_exp3_hyperopt(project, foldername, group_names, metric="-elbo"):
    pass


def format_row(secondaries, secondary_metrics):
    larger_is_better = False
    if secondary_metrics[0] == 'num_detected_modes':
        secondary_format = "elbo_format"
        larger_is_better = True
    elif secondary_metrics[0] == 'MMD:':
        secondary_format = "mmd_format"
    return secondary_format, larger_is_better


def latex_format(metrics, format, larger_is_better=False):
    return None


if __name__ == "__main__":
    fetch_exp3_eval("mini/gmmvi-eval", "Planar4_EVAL",
                    ["samtrux_planar_4", "sepyfux_planar_4"],
                    secondary_metrics=["MMD:"],
                    bad_run_ids=["aaaa01", "aaaa02"  # sepyfux
                    ])
    fetch_exp3_eval("mini/gmmvi-eval", "GMM20_EVAL",
                    ["samtrux_gmm20"],
                    secondary_metrics=["num_detected_modes"])
    fetch_exp3_hyperopt("mini/gmmvi-search", "Planar4", ["samtrux_planar_4"])
'''

README = """Experiment 3 (miniature fixture)
---------------------------------

The 3-seed evaluations were started by the scripts in ``evaluations``.  We observed
instabilities for Sepyfux on Planar Robot and decided to exclude the corresponding
seeds when computing the reported values:

- SEPYFUX on Planar Robot: 2 bad seeds
"""


def cw2_doc(group: str, experiment: str, algorithm: str, repetitions: int) -> str:
    return f"""---
name: "DEFAULT"
iterations: {1000000 if repetitions > 1 else 100000}
repetitions: {repetitions}
algorithm_id: "{algorithm}"
wandb:
    project: gmmvi-eval

---
name: "{group.split("/")[-1]}"
experiment_id: "{experiment}"
wandb:
    group: "{group}"
"""


def run_config(algorithm: str) -> str:
    return f"""algorithm_id:
  desc: null
  value: {algorithm}
iterations:
  desc: null
  value: 1000000
repetitions:
  desc: null
  value: 3
"""


def history(rows: list[tuple[int, float, float]], columns: list[str]) -> str:
    header = ",".join(["", "_step", "num_samples", "_runtime"] + columns)
    lines = [header]
    for step, primary, secondary in rows:
        lines.append(f"0,{step},{step * 3000},{step / 10.0},{primary},{secondary}")
    return "\n".join(lines) + "\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


FAMILIES = {
    # family dir -> (primary column, secondary column, [(elbo, secondary, bad)])
    "Planar4_EVAL/samtrux_planar_4": (
        "-elbo",
        "MMD:",
        [(10.0, 0.010, False), (11.0, 0.020, False), (12.0, 0.030, False)],
    ),
    "Planar4_EVAL/sepyfux_planar_4": (
        "-elbo",
        "MMD:",
        [(1.0, 0.5, False), (2.0, 0.6, False), (100.0, 9.0, True), (200.0, 8.0, True)],
    ),
    "GMM20_EVAL/samtrux_gmm20": (
        "-elbo",
        "num_detected_modes",
        [(5.0, 8.0, False), (7.0, 10.0, False)],
    ),
}


def main() -> None:
    write(REPO / "evaluations" / "fetch_exp3.py", FETCH)
    write(REPO / "README.rst", README)
    write(
        REPO / "evaluations" / "configs" / "exp3 (eval)" / "samtrux.yml",
        cw2_doc("samtrux_planar_4", "planar_robot", "SAMTRUX", 3)
        + '---\nname: "GMM20"\nexperiment_id: "gmm20"\nwandb:\n    group: "samtrux_gmm20"\n',
    )
    write(
        REPO / "evaluations" / "configs" / "exp3 (eval)" / "sepyfux.yml",
        cw2_doc("sepyfux_planar_4", "planar_robot", "SEPYFUX", 3),
    )
    write(
        REPO / "evaluations" / "configs" / "exp3 (hyperopt)" / "samtrux.yml",
        cw2_doc("samtrux_planar_4", "planar_robot", "SAMTRUX", 1),
    )

    for family, (primary, secondary, runs) in FAMILIES.items():
        directory = RESULTS / family
        algorithm = "SAMTRUX" if "samtrux" in family else "SEPYFUX"
        for index, (elbo, second, bad) in enumerate(runs):
            suffix = ".csv.bad" if bad else ".csv"
            rows = [
                (1000 * (k + 1), elbo * (k + 1) / 2.0, second * (k + 1) / 2.0) for k in range(3)
            ]
            rows[-1] = (rows[-1][0], elbo, second)
            write(directory / f"run_{index}{suffix}", history(rows, [primary, secondary]))
            write(directory / f"run_{index}_config.yml", run_config(algorithm))

    cells = [
        {
            "family": "Planar4_EVAL/samtrux_planar_4",
            "metric": "-elbo",
            "value": 11.00,
            "spread": 1.41,
            "decimals": 2,
        },
        {
            "family": "Planar4_EVAL/samtrux_planar_4",
            "metric": "MMD:",
            "value": 0.02,
            "spread": 0.0141,
            "decimals": 4,
        },
        {
            "family": "Planar4_EVAL/sepyfux_planar_4",
            "metric": "-elbo",
            "value": 1.50,
            "spread": 1.06,
            "decimals": 2,
        },
        {
            "family": "GMM20_EVAL/samtrux_gmm20",
            "metric": "-elbo",
            "value": 6.00,
            "spread": 2.12,
            "decimals": 2,
        },
        {
            "family": "GMM20_EVAL/samtrux_gmm20",
            "metric": "num_detected_modes",
            "value": 9.00,
            "spread": 2.12,
            "decimals": 2,
        },
    ]
    import json

    write(ROOT / "reported_matched.json", json.dumps({"cells": cells}, indent=1) + "\n")
    wrong = [dict(cell) for cell in cells]
    for cell in wrong:
        if cell["family"] == "Planar4_EVAL/sepyfux_planar_4":
            cell["value"] = 5.00  # not what the two surviving seeds average to
    write(ROOT / "reported_mismatch.json", json.dumps({"cells": wrong}, indent=1) + "\n")
    print(f"mini fixture written to {ROOT}")


if __name__ == "__main__":
    main()
