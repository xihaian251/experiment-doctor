"""Runtime capture primitives: git, environment, invocation facts.

Every capture function returns an evidence-graded ``ProvenanceField`` and never
raises for missing information: an unobservable fact comes back ``UNKNOWN``
with no value (the v0.1 discipline).  Stdlib only -- git is called through
``subprocess``, no GitPython.
"""
