"""The three-way coverage split. ONE implementation, shared by every report.

`DECISIONS.md` sec 48. The single coverage figure it replaces collapsed three
different things into one:

  answered             the resolver made a composition claim
  not_determinable     it could not -- `Unresolved` / `Ambiguous`
  record_contradicted  it MUST NOT -- `AttestationDiscrepancy`, where the
                       sources disagree and contract 4.2 forbids asserting a
                       composition

Only the middle one is a coverage shortfall. Folding the third in made the
metric DECLINE AS DETECTION IMPROVED: `datasets_v2` plants one false
attestation per dataset, the resolver caught 13 of 13, and its coverage fell
from 85% to 79% BECAUSE it caught them.

This module exists so the split is computed once. Three reports quoted the old
figure and they would have drifted apart; `CLAIMS.md` exists because that
already happened once.
"""

from __future__ import annotations

#: The four scopes. Every published coverage figure names one of these -- a
#: scope-less coverage number is what let 85% read as a corpus-wide claim when
#: it is the original-fourteen scope.
SCOPES: dict[str, str] = {
    "all": "all 30 datasets",
    "non_absence": "the 28 datasets carrying a PSP settlement artefact",
    "absence": "the 2 PSP-absence datasets",
    "original_14": "the original 14 -- the scope THREE_SYSTEMS.md publishes",
}


def in_scope(dataset: str, scope: str) -> bool:
    absence = "Bnone" in dataset
    if scope == "all":
        return True
    if scope == "non_absence":
        return not absence
    if scope == "absence":
        return absence
    if scope == "original_14":
        return dataset.startswith("datasets/") and not absence
    raise KeyError(f"unknown scope {scope!r}; expected one of {sorted(SCOPES)}")


def split(rows: list[dict], scope: str = "all") -> dict:
    """Aggregate the per-dataset coverage split over one named scope."""
    keys = ("settlement_lines", "answered", "not_determinable",
            "record_contradicted", "no_outcome")
    out = {k: 0 for k in keys}
    out["datasets"] = 0
    for row in rows:
        if not in_scope(row["dataset"], scope):
            continue
        cover = row.get("coverage")
        if cover is None:
            raise KeyError(
                f"{row['dataset']} has no `coverage` block. Re-run "
                "`python3 corpus/score_resolver.py --all` -- this results "
                "file predates DECISIONS.md 48 and its coverage figure is the "
                "collapsed one.")
        for k in keys:
            out[k] += cover[k]
        out["datasets"] += 1
    out["scope"] = scope
    out["scope_label"] = SCOPES[scope]
    #: The denominator that answers the question a reader is actually asking:
    #: of the lines where a composition claim IS the appropriate answer, how
    #: many did the resolver make?
    determinable = out["answered"] + out["not_determinable"]
    out["determinable"] = determinable
    out["on_determinable_pct"] = (100 * out["answered"] / determinable
                                  if determinable else None)
    out["of_all_lines_pct"] = (100 * out["answered"] / out["settlement_lines"]
                               if out["settlement_lines"] else None)
    return out


def sentence(s: dict) -> str:
    """One line a reader can quote without losing the scope."""
    if not s["settlement_lines"]:
        return f"no settlement lines in scope ({s['scope_label']})"
    determinable = (f"{s['answered']}/{s['determinable']} "
                    f"({s['on_determinable_pct']:.1f}%)"
                    if s["determinable"] else "no determinable lines")
    return (f"{s['scope_label']}: {s['answered']} answered, "
            f"{s['not_determinable']} not determinable, "
            f"{s['record_contradicted']} record contradicted, of "
            f"{s['settlement_lines']} settlement lines -- coverage on lines "
            f"where a composition claim is the appropriate answer is "
            f"{determinable}")


def table(rows: list[dict], scopes=tuple(SCOPES)) -> list[str]:
    """The markdown block every report shares, so none of them can drift."""
    out = ["| scope | settlement lines | answered | not determinable | "
           "record contradicted | **coverage on determinable lines** |",
           "|---|---:|---:|---:|---:|---:|"]
    for scope in scopes:
        s = split(rows, scope)
        if not s["settlement_lines"]:
            continue
        pct = (f"**{s['answered']}/{s['determinable']} "
               f"({s['on_determinable_pct']:.1f}%)**"
               if s["determinable"] else "—")
        out.append(f"| {s['scope_label']} | {s['settlement_lines']} | "
                   f"{s['answered']} | {s['not_determinable']} | "
                   f"{s['record_contradicted']} | {pct} |")
    out += ["",
            "**`record contradicted` is a finding, not a shortfall.** Those "
            "are lines where two sources disagree and contract §4.2 forbids "
            "asserting a composition. Counting them as coverage misses made "
            "the metric fall as detection improved (`DECISIONS.md` §48)."]
    return out
