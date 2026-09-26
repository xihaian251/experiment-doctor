# ED003 — Historical Code Provenance

## Purpose
Can a run be bound to the code revision that actually executed, rather than to whatever
the repository contains today?

## Applies To
`run`. One result per discovered run.

## Inputs
`ExperimentRun.code_commit`, `.code_repository`, `.code_dirty`, `.artifacts`.

## PASS
The commit is `CONFIRMED`/`SUPPORTED` **and** its source is one of this run's own
artifacts (measured as `source_kind`, e.g. `LOG`). The summary names the revision.

## FAIL
The run's artifacts give mutually exclusive revisions (`CONFLICTING`). Severity HIGH:
one run cannot have executed two different commits.

## INCONCLUSIVE
- No artifact records a revision. The summary is exactly
  `historical code identity cannot be established from available artifacts`.
- A revision is named, but by a file this run did not produce (for example a README or
  a release note). Named-by-somebody-else is not attested-by-this-run.

## NOT_APPLICABLE
Not produced — every run has a code identity question to answer, even when the answer is
that it cannot be established.

## NOT_RUN
Never produced by this rule; the engine emits it if evaluation raises.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM (absence of a revision is a documentation gap about
the past, not an experimental error).

## Evidence
`code_commit` value with its grade and citation, `code_repository` with its grade,
`code_dirty`, and whether any artifact attached to the run carries the revision.

## Limitations
- The present checkout is never substituted for the code that ran, in any branch.
- When the working-tree state is also unrecorded, that is stated: the revision alone
  would not prove the tree was clean.

## Examples
- GMMVI: 3483/3483 runs INCONCLUSIVE with the canonical wording above; the Phase 0
  results folder holds no per-run revision.
- TorchSSL: 6/6 runs INCONCLUSIVE for the same reason — the logs record the command, not
  the sha.
- Synthetic: a run whose `log.txt` writes `commit=abc123` → PASS with
  `source_kind == "LOG"`.
