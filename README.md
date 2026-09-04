<p align="center">
  <img src="settlrlogoblue.png" alt="Settlr" width="220">
</p>

<p align="center">
  <a href="https://github.com/devapragadeesh/Settlr/actions/workflows/ci.yml"><img src="https://github.com/devapragadeesh/Settlr/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

# Settlr

*[`AGENTS.md`](AGENTS.md) describes this repo's layout to a coding agent.
[`dashboard/`](dashboard/) is the generated product UI.*

## What Settlr does

A payment processor settles many transactions into one bank credit at a
time it chooses, net of fees and refunds — a single ₹99,329.23 deposit
might be 21 orders or 40, and the bank statement alone never says which.
Get that match wrong at scale and finance either books revenue that never
settled or misses revenue that did.

Settlr reconciles the payment ledger, the bank statement, the ERP order
book and GST filings against each other, matches what it can prove — and
refuses to guess on the rest, with a stated reason. That refusal is the
whole point: a reconciliation tool that always names an answer is guessing
on every batch with more than one arithmetically valid explanation, and
cannot tell you which ones those were.

## Inside the dashboard

**Ask Settlr — a real AI assistant, not a keyword matcher.** A chat panel
answers questions about the live reconciliation in plain English: what's
ambiguous and why, why the match rate reads the way it does, what to work
on first. It runs on a genuine Claude integration (`agents/chat_answerer.py`)
that drafts its own read-only SQL against the run's real results and
summarizes what comes back — every answer carries its reasoning, concrete
next steps, and the record it's citing, not just a headline. If the model
is unreachable it degrades to a deterministic local answerer over the same
data rather than failing silently.

**A team of narrow agents, gated behind human approval.** Five more Claude-
narrated agents sit behind `/` in the same panel — an SLA watchdog that
drafts escalations on aging breaks, a queue cleaner that separates timing
differences provably inside their settlement window from the rest, a break
investigator and an ambiguity arbiter that each draft a proposal for a
human to accept or reject, and an ITC drafter that cites the actual GST
provision behind a flagged input-tax-credit risk. None of them assigns or
classifies a row on its own authority — every proposal lands in a real
maker-checker approval queue (`agent_approval_requests`) and nothing is
final until a person clears it.

**A workflow, not a report.** An exceptions queue routed by owner and
aging, with a full evidence drawer per item. A journal workflow that
validates its own balance (debits = credits, journal net ties to the
ledger) before it lets you approve, and generates the actual posting
document on demand. A settlement-timing view built from real payment
timestamps — mean time to settle, unsettled exposure by age — not assumed
from the ledger. Both a dark and a light theme.

```bash
python3 dashboard/build_dashboard.py   # writes dashboard/index.html
python3 -m http.server 8935            # open it at localhost:8935
```

## The result that motivated the whole design

On the datasets where payment records get corrupted, a naive engine that
trusts every record it's given asserts confidently wrong compositions with
no way to signal doubt. Settlr's evidence-tiered resolver, scored by the
same benchmark, asserts **zero** wrong compositions on the same data and
correctly flags the corrupted records as findings instead. On the primary
benchmark set, it answers **92.9%** of the lines it is actually able to
answer (276 of 297 determinable settlement lines across all 30 entities),
and abstains — rather than guesses — on the rest.

The full per-dataset comparison against a naive baseline and the previous
engine, generated from a live run: **[`corpus/THREE_SYSTEMS.md`](corpus/THREE_SYSTEMS.md)**.

## How matching works

A settlement batch is a *subset* of eligible payments — Razorpay's own
documentation states that "when settling transactions, we will only choose
the ones that add up to your current live balance." So a bank credit does
not by itself identify which ledger rows composed it, and often several
different subsets close to the same amount. Settlr's resolver is a
4-stage cascade — exact join → fuzzy fallback → CP-SAT subset-sum
reconstruction → deterministic exception routing — that assigns a row only
when it can name the evidence behind the assignment (which parties
independently corroborate it), and reports the number of rival
compositions that would have passed the identical check when it can't.
The LLM narrates findings; it never matches.

## Architecture

```
resolver_contract/   the outcome vocabulary — Verified, Reconstructed,
                      Ambiguous, Unresolved, OpenBreak — interface only.
resolver/             the matching cascade.
corpus/               the benchmark: seeded datasets, oracle, leak audit.
ingest/ transport/    parses CSV/JSON/.xlsx/CAMT.053/MT940/JSONL; pluggable
store/ service/       SFTP/S3 pulls; SQLite persistence with a full
                      row-level audit trail; a pipeline, scheduler and API.
agents/               Claude-narrated agents — see "Inside the dashboard".
dashboard/            the generated product UI.
```

The dependency direction is one-way and enforced by tests that scan
imports by AST, not by convention: `ingest/`, `transport/`, `store/`,
`service/`, `dashboard/` and `agents/` never import `resolver/` or
`resolver_contract/` directly, and only `eval/`/`corpus/oracle.py` may ever
read the benchmark's isolated answer key. `git log` shows the benchmark
contract, its seeds, and its datasets committed in that order, before the
resolver being scored ever existed — a resolver frozen before scoring
cannot be tuned to the scorer, which is checkable rather than asserted.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-service.txt

pytest tests engine/tests corpus/tests resolver/tests -q   # ~30s
python3 dashboard/build_dashboard.py && python3 -m http.server 8935 -d dashboard
```

That's the whole cold-start path. `run_all.py` additionally reproduces the
full three-system comparison above from scratch (naive baseline, previous
engine, and this resolver, over every dataset) — slower, and not needed to
verify the tests pass or to see the product.

## Engineering rigor, if you want to check it yourself

Every number in this README traces to a script, not a hand-typed claim.
**[`CLAIMS.md`](CLAIMS.md)** lists every quantitative claim with its
denominator and scope; **[`SCORECARD.md`](SCORECARD.md)** is the five-
minute version. **[`DECISIONS.md`](DECISIONS.md)** is the append-only,
numbered record of every non-trivial design call in this project, each one
carrying the alternative that was rejected and why — including the defects
this project found in its own earlier work and how they were measured,
not just claimed fixed. **`investigation/`** holds the dated, evidence-
first write-ups behind that record (a malformed-input robustness suite, a
throughput ceiling, a controls mapping, an actively-tracked resolver-timing
property under CI runner contention — `investigation/resolver_nondeterminism/`).
None of it is summarized away here; it's linked because it's long, not
because it's hidden.

```bash
# verify the frozen primary dataset has not been altered
shasum -a 256 -c <(sed 's|^\([0-9a-f]*\) |\1  |' engine/DATASET_HASHES.txt)
```
