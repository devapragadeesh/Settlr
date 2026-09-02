"""A real GST/ITC population, sibling to `bank_side_errors.py`. `DECISIONS.md`
§55.

## What this replaces, and why it existed at all

`corpus/generator/build.py`'s `build_erp_and_gst` used to plant exactly three
ITC findings at three fixed indices -- `gst_rows[0]` always got Rule 37A,
`gst_rows[1]` was always dropped for Sec 16(2)(aa), and the new `gst_rows[1]`
(after the drop) always got Rule 48(5). Every dataset that ever called it
produced the identical three-line finding, in the identical shape, at the
identical position. `corpus/CORPUS_SPEC.md`'s own limitations table names this
as D9: a 20-row file, three single-column filters at precision 1.000, no
volume, no partially-filed-supplier population, no IRN-presence population.
This module is the fix: fractional, seeded, independently-drawn selection over
however many gateway invoices the axis point actually produces, so a filter's
precision/recall is measured against a population instead of a fixed index.

## Why GATEWAY-line variation, not vendor-line variation, is what matters here

`matching/stage4_exceptions.py::_tax_exceptions()` computes
`supplier_lines = [line for line in dataset.gstr2b if line.gstin ==
findings.supplier_gstin]` before it does anything else. Every one of its three
statutory checks -- `gstr2b_absent` (derived from `monthly_accrual` months with
no matching `supplier_lines` entry), `gstr2b_no_irn` (`not line.has_irn` over
`supplier_lines`), `gstr2b_37a_exposure` (`supplier_gstr3b_filed == "N"` over
`supplier_lines`) -- only ever looks at lines already filtered down to the
identified gateway GSTIN. The third-party vendor lines `build_erp_and_gst`
also generates (the `len(gst_rows) * multiplier + 12` loop) are invisible to
all three filters; they exist purely as `identify_supplier()`'s search space,
so that finding the gateway's own GSTIN is itself a nontrivial reconciliation
step (tie invoice taxable values to the accrued fee ledger month by month)
rather than a label already sitting on the row. Varying the vendor pool
(`gst_vendor_noise_multiplier`) therefore tests a *different* thing --
`identify_supplier()`'s robustness as the haystack grows -- and is kept as a
separate knob from the three ground fractions here, on purpose: mixing the two
into one parameter would make a finding in one hide inside the other.

## Why "IRN generated more than 30 days late" is not modelled

Both `engine/generator.py`'s and this corpus's own commentary already
establish the reason: India's e-invoicing IRP refuses to register an e-invoice
outside its acceptance window, so a document that would have been "late" never
gets an IRN and never auto-populates into 2B at all. There is no way to
distinguish "generated late" from "absent from 2B" in the data the tax
authority would actually produce -- they are the same row, indistinguishable
by construction, not two different grounds. Modelling a fourth "late IRN"
ground would therefore either (a) silently duplicate the absent-from-2B ground
under a different name, or (b) mint a row shape the IRP could never produce,
which is exactly the kind of unearned realism `DECISIONS.md` disciplines
against. It stays a documented absence, not a plant.

## The honesty discipline, mirroring `plant_mispost` / `plant_false_composition`

No row is ever minted. This function only selects among gateway invoices that
`build_erp_and_gst` already built from the real fee ledger, and mutates
existing fields on existing rows (or drops a row entirely for the
absent-from-2B ground) -- the same three field-level mutations the fixed-index
plant already made, just applied to a sampled set instead of a fixed index.
If a fraction rounds down to zero eligible invoices, that ground is simply not
planted at this axis point; the caller gets an empty contribution for it,
never a forced one.

## The three selections, and why two of them may overlap on purpose

1. **Absent-from-2B** (`absent_fraction`): a disjoint subset of
   `gateway_invoices`, sized `floor(absent_fraction * len(gateway_invoices))`,
   removed from `gst_rows` entirely -- there is nothing at that invoice number
   in the file, exactly like the old `gst_rows.remove(dropped)`.
2. **No-IRN** (`no_irn_fraction`) and **Rule 37A** (`filed37a_fraction`) are
   each drawn INDEPENDENTLY from the survivors (the gateway invoices NOT
   selected for ground 1). Independent draws means a single invoice can land
   in both sets. That is intentional, not an edge case to avoid: the fixed
   three-index plant could never produce an invoice carrying two grounds at
   once, and a resolver (or the frozen filters) that only ever sees one ground
   per invoice has never been asked "does this invoice show up under BOTH
   `gstr2b_no_irn` and `gstr2b_37a_exposure`, or does only one filter fire?"
   This is precisely the "compounding grounds" case `DECISIONS.md` §55 is
   named for.
"""

from __future__ import annotations

import random
from collections import OrderedDict
from fractions import Fraction

__all__ = ["plant_itc_population"]


def _paise(rupee_string: str) -> int:
    """Inverse of `bank.rupees`: an exact rupee string -> integer paise.

    Not a float parse -- `rupee_string` was produced by `rupees()`'s own
    divmod, so this is a plain string split, matching `DECISIONS.md`'s
    "money is integer paise everywhere, no float arithmetic" rule even in a
    module that only reads money back out of a CSV-shaped field.
    """
    negative = rupee_string.startswith("-")
    body = rupee_string[1:] if negative else rupee_string
    whole, _, frac = body.partition(".")
    frac = (frac + "00")[:2]
    value = int(whole or "0") * 100 + int(frac or "0")
    return -value if negative else value


def _tax_total_paise(row: OrderedDict) -> int:
    """igst + cgst + sgst, in paise. Gateway lines carry igst=0, so this is
    the same `cgst + sgst` `engine/generator.py`'s `itc_paise` uses, computed
    the same way -- summed from the row's own three tax columns rather than
    re-derived, so it can never disagree with what actually ended up in the
    file.
    """
    return _paise(row["igst"]) + _paise(row["cgst"]) + _paise(row["sgst"])


def plant_itc_population(
    gst_rows: list[OrderedDict],
    gateway_invoices: list[str],
    rng: random.Random,
    *,
    absent_fraction: Fraction,
    no_irn_fraction: Fraction,
    filed37a_fraction: Fraction,
) -> tuple[list[OrderedDict], list[dict]]:
    """Plant a real, fractional ITC-at-risk population over the gateway's own
    2B lines. Returns a NEW `gst_rows` list (the input is not mutated) and one
    ground-truth entry per (invoice, ground) pair, each shaped exactly like
    the entries the fixed-index plant used to produce, plus `itc_paise`.

    `gst_rows` at call time already contains the gateway's monthly lines AND
    the third-party vendor-noise lines `build_erp_and_gst` builds alongside
    them -- this function only ever selects from `gateway_invoices` and only
    ever touches rows whose `invoice_no` is in that list. Vendor lines pass
    through unexamined and unmutated.
    """
    total = len(gateway_invoices)
    absent_n = int(absent_fraction * total)
    absent_invoices = (set(rng.sample(gateway_invoices, absent_n))
                       if absent_n > 0 else set())

    survivors = [inv for inv in gateway_invoices if inv not in absent_invoices]

    no_irn_n = int(no_irn_fraction * len(survivors))
    no_irn_invoices = (set(rng.sample(survivors, no_irn_n))
                       if no_irn_n > 0 else set())

    filed37a_n = int(filed37a_fraction * len(survivors))
    filed37a_invoices = (set(rng.sample(survivors, filed37a_n))
                         if filed37a_n > 0 else set())

    by_invoice = {row["invoice_no"]: row for row in gst_rows
                 if row["invoice_no"] in gateway_invoices}

    new_rows: list[OrderedDict] = []
    itc_at_risk: list[dict] = []
    for row in gst_rows:
        invoice_no = row["invoice_no"]
        if invoice_no in absent_invoices:
            # Sec 16(2)(aa): the invoice never reached 2B at all. Dropped, not
            # kept with a blank -- an absent invoice is absent from the file,
            # exactly like the old `gst_rows.remove(dropped)`.
            original = by_invoice[invoice_no]
            itc_at_risk.append({
                "invoice_no": invoice_no,
                "period": original["gstr1_filing_period"],
                "reason": "absent_from_gstr2b",
                "statute": "Sec 16(2)(aa) CGST",
                "itc_paise": _tax_total_paise(original),
            })
            continue

        new_row = OrderedDict(row)
        if invoice_no in no_irn_invoices:
            # Rule 48(5): no valid IRN, so it is not a tax invoice.
            new_row["irn"] = ""
            new_row["itc_availability"] = "No"
            itc_at_risk.append({
                "invoice_no": invoice_no,
                "period": new_row["gstr1_filing_period"],
                "reason": "no_irn_on_notified_supplier_invoice",
                "statute": "Rule 48(5) CGST",
                "itc_paise": _tax_total_paise(new_row),
            })
        if invoice_no in filed37a_invoices:
            # Rule 37A: supplier has not filed GSTR-3B. 2B does NOT flag this
            # -- itc_availability still reads Yes -- which is why it is the
            # interesting exposure: the recon engine has to COMPUTE it.
            new_row["supplier_gstr3b_filed"] = "N"
            itc_at_risk.append({
                "invoice_no": invoice_no,
                "period": new_row["gstr1_filing_period"],
                "reason": "supplier_gstr3b_not_filed_rule_37a",
                "statute": "Rule 37A CGST",
                "itc_paise": _tax_total_paise(new_row),
            })
        new_rows.append(new_row)

    return new_rows, itc_at_risk
