# Settlement Truth Engine — dataset, simulator, and freeze

This directory contains **data and tests only**. No matching, solving or
reconciliation logic exists here, by design — see [the freeze](#the-freeze).

| file | what it is |
|---|---|
| [`SETTLEMENT_SPEC.md`](SETTLEMENT_SPEC.md) | the normative rule, with the verbatim Razorpay quote and URL it implements |
| [`GENERATION_REPORT.md`](GENERATION_REPORT.md) | class counts, provenance distribution, and what is *not* claimed — every figure derived from the data on disk |
| [`ROBUSTNESS.md`](ROBUSTNESS.md) | the planted classes across 20 seeds nobody chose — the answer to "you tuned it until it worked" |
| `simulator.py` | the settlement batching engine. Implements `SETTLEMENT_SPEC.md` and nothing else |
| `generator.py` | builds the ledger, plants the 15 classes, emits the dataset and the isolated key |
| `report.py` | regenerates `GENERATION_REPORT.md` from the frozen files |
| `robustness.py` | multi-seed sweep; writes `ROBUSTNESS.md` |
| `data/` | the solver-visible dataset |
| `ground_truth/` | the answer key. **No solver module may read this path** |
| `DATASET_HASHES.txt` | SHA-256 of every data file and of the key |
| `tests/` | written *before* any solver exists |

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python engine/generator.py --seed 20260822
.venv/bin/python engine/report.py
.venv/bin/python engine/robustness.py --seeds 20     # slow, a few minutes
.venv/bin/python -m pytest engine/tests/ -q
```

## Why the data is synthetic

Razorpay test mode never produces settlements. Instant settlement — the only
forcing mechanism — is blocked server-side with reason code
`instant_settlements_test_mode_blocked`, reproduced identically through REST,
the hosted MCP server and the CLI. The evidence is in
an internal spike.

Settlement batching here is therefore **synthesized from Razorpay's documented
behaviour, not captured**. Every row carries a `source_tier` saying which of
`captured_real` / `synthesized_documented` / `synthesized_modelled` it sits at,
and a `source_ref` naming the exact citation. Nothing claims to be captured
settlement data, because nothing is.

## The freeze

The dataset was generated, hashed and committed **before a single line of
solver code was written**. The commit timestamp is the defence against "you
only planted cases you knew you could solve."

**But a timestamp is weaker evidence than it looks**, and the repo says so
rather than overselling it. The dataset is a pure function of one seed, so a
commit time cannot rule out trying seeds until the numbers looked good, and
`DATASET_HASHES.txt` is written by the generator into the same commit — it is
tamper detection, not an attestation of authorship order.

Three properties make the claim checkable rather than merely asserted:

- `tests/test_determinism.py` re-runs the generator from seed and asserts the
  committed bytes are byte-identical to a fresh run, three runs in a row. The
  data cannot be quietly hand-edited after the fact.
- `tests/test_ambiguity.py` encodes a class of batch that is **provably
  unresolvable** — two distinct subsets of eligible payments sum to the same
  bank credit. It asserts that a solver returning one confident answer for such
  a batch **fails**, even when it names the subset the simulator actually
  picked. That test was written before the solver, so the solver cannot be
  built wrong.
- [`ROBUSTNESS.md`](ROBUSTNESS.md) runs the generator over seeds `0..19` and
  reports min / median / max for every planted class. If the classes appear
  reliably across seeds nobody chose, the *generator* is honest — a stronger
  claim than any one dataset being frozen. The shipped seed was selected only
  to land on exactly 240 rows.

## What independent audit changed

Three reviewers went at this before the freeze. What they found is recorded
rather than quietly fixed, because the findings are more informative than the
fixes:

- **Two ground-truth leaks.** `source_ref` named the mechanism that created a
  row (`grep ambiguity-calibration` identified both unresolvable batches), and
  calibration refunds used a `notes.reason` value no organic refund used. Both
  are closed, and `tests/test_no_leakage.py` now checks provenance strings and
  note *values*, not just keys. See `SETTLEMENT_SPEC.md` §8.1.
- **Two false claims about a vendor.** UPI was priced at zero — Razorpay's
  published pricing bills it at 2% — and Amex was priced at 2% rather than 3%.
  Both corrected; see §4.2.
- **One mechanically impossible scenario.** A GSTR-2B line with an IRN
  generated more than 30 days late cannot exist: the IRP refuses to register
  the document, so no IRN is produced and nothing populates 2B. Replaced with
  the Rule 48(5) missing-IRN case and a Rule 37A exposure; see §9.3.
- **A silently under-delivering generator.** Three ambiguity plants were
  declared and two landed, with no test noticing. Plants now record their own
  failures in the key, and a test asserts every declared plant is accounted for.
