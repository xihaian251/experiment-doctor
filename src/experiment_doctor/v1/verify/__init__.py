"""Phase 3 verify: deterministic validation of an evidence bundle.

The verifier never *repar* anything: it recomputes hashes, checks membership
and reports.  The bundle (or the project) is the only write target, for its
own ``verify.json`` / ``verify.md`` outputs, and there is deliberately no
score, confidence or trust field anywhere in the report.
"""
