"""Miniature stand-in for the project's fetch script.

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
