"""Pluggable transports for pulling files that did not originate on this
machine. Layered strictly downstream of `resolver/` and `ingest/` --
`tests/test_layer_isolation.py` enforces that `resolver/` never imports this
package, the same way it enforces `ingest/`.

Every backend implements the same three-method `Transport` protocol
(`transport/base.py`). Every test in this package runs against
`RecordedTransport` (`transport/recorded.py`), which replays a fixture tree on
disk rather than making a network call -- the pattern `spike/common.py`
already established: persist each request/response pair verbatim, with
credentials redacted, and let that recording be the evidence trail as well as
the test fixture.

`transport/credentials.py::require_non_production` is the refusal guard,
directly modelled on `spike/common.py::load_env`'s hard exit on a live
Razorpay key: *"LIVE KEYS ARE FORBIDDEN IN THIS SPIKE."* The same shape here:
refuse to run against a transport not explicitly marked non-production unless
an opt-in environment variable is set.
"""
