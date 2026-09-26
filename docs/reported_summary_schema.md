# Reported-summary input file (`--reported-table`)

`experiment-doctor audit` recomputes every aggregation from the run-level artifacts it
finds on disk. Whether the recomputed number agrees with the number the project
*published* cannot be recovered from run artifacts alone, so published values are an
explicit external input. When no file is passed, `reported_value` stays `None` and every
comparison is `UNKNOWN` — the tool never guesses a published number.

## Shape

```json
{
  "source": "where the transcription came from",
  "cells": [
    {
      "family": "Planar4_EVAL/samtrux_planar_4",
      "metric": "-elbo",
      "variant": "included",
      "value": 11.47,
      "spread": 0.05,
      "decimals": 2,
      "source": "Table 8, p.29, PlanarRobot -ELBO column Samtrux"
    }
  ]
}
```

| key | required | meaning |
|---|---|---|
| `family` | yes | `ExperimentFamily.family_id` as produced by the adapter (`<result_dir>/<group>`) |
| `metric` | yes | metric column name exactly as it appears in the run history CSV |
| `variant` | no (default `included`) | which aggregation membership the cell corresponds to: `included` (the project's own membership rule) or `all_completed` |
| `value` | yes | the published central statistic |
| `spread` | no | the published `+/-` number |
| `decimals` | no | digits after the decimal point of the printed cell |
| `value_tolerance` | no | overrides the tolerance used for `value` |
| `spread_tolerance` | no | overrides the tolerance used for `spread` |

## Tolerances

Comparison is numeric, never string comparison (`audit.close_enough`):

```
abs(recomputed - reported) <= tolerance
```

* `decimals: d` implies `tolerance = 0.5 * 10**-d` (the printed rounding half-width),
  with a relative `1 + 1e-9` slack so a value exactly on a rounding boundary is not
  flagged.
* `value_tolerance` / `spread_tolerance` override that, and are needed whenever a cell
  is printed in scientific notation, because then the half-width depends on the
  exponent, not on a fixed digit count. A cell printed with `%.1e` as `1.6e-2` has
  half-width `5e-4`; a spread printed with `%.0e` as `8e-4` has half-width `5e-5`.
* When only `value` is given, `spread` is not compared: a `MATCH` requires the mean to
  agree and does not require a spread the file does not contain.

## Verdict vocabulary

`MATCH` — mean within tolerance and, if a spread was provided, spread within tolerance.
`MISMATCH` — either check failed.
`UNKNOWN` — no reported cell, no recoverable member values, or a non-finite number.
`statistic != "mean"` is always `UNKNOWN` in v0.1: v0.1 recomputes means only.

## What this file is *not*

It is a transcription of published results, nothing else. It must not contain
values recomputed by this tool: that would make the comparison circular. Cells whose
`variant` is `all_completed` are therefore absent from `examples/gmmvi_reported_table.json`
— no such counterfactual number is published anywhere.
