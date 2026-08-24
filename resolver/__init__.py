"""The resolver. Imports `resolver_contract` and nothing else from this repo.

No module under `resolver/` may import, read, open or path-reference any
`ground_truth.json`. Enforced by `resolver/tests/test_isolation.py`, which was
verified to FAIL when the rule is deliberately violated -- a test nobody has
seen fail is a test nobody has run, and that exact gap is how defect D2
shipped inside a 268-test suite.
"""
