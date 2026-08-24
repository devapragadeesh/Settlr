"""corpus/leakage_audit.py -- search for leaks, do not check a list.

## Why this is a search and not a checklist

Four leaks have been found in this project's data, by four different readers,
and closed one at a time:

1. `source_ref` named the mechanism ("ambiguity-calibration debit").
2. a `notes` value was a 100%-precision marker (`partial_cancellation`).
3. the six orphan ERP invoices carry the six highest invoice numbers.
4. calibration debits are findable by "large debit adjustment, null dispute_id"
   -- and both provably-ambiguous batches sit in the batches that got them.

Each was closed by adding a token to a deny-list. The fifth will not be a
token. So this module does not ask *"does the string 'calibration' appear"*; it
asks *"is there ANY predicate over the solver-visible columns that separates a
planted class from the organic population better than chance"* -- and then
reports the strongest one it can find, whether or not anyone anticipated it.

## What it tests, per planted class

| family | question |
|---|---|
| `single_column` | can one column's value, threshold or null-pattern separate planted from organic? |
| `column_pair`   | can a conjunction of two such predicates? |
| `ordering`      | do file position or any field's ordinal rank concentrate the class? |
| `derivability`  | is any field a function -- string, arithmetic or ordering -- of any other field or combination? |
| `distributional`| KS test on every numeric column, planted vs organic |

## Why every finding carries a p-value

Precision alone is not evidence. Two planted batches out of twelve will land
inside some three-batch predicate by luck more often than intuition suggests,
and a search that evaluates tens of thousands of predicates will find several
perfect separators in pure noise. So every candidate separator is scored with a
one-sided hypergeometric tail probability -- *given this class size and this
predicate's support, how often would chance do at least this well* -- and the
significance threshold is Bonferroni-corrected by the number of hypotheses the
search actually evaluated. That number is reported. A separator that survives
that is a leak; one that does not is an artefact of looking hard.

## Validation

`--validate-frozen` runs the audit against `engine/data/` and asserts it
independently rediscovers D4, D5, D6 and D7. An audit that cannot find the
leaks we already know about proves nothing about the ones we do not.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --------------------------------------------------------------------------
# thresholds -- stated here, once, so a build failure is never a surprise
# --------------------------------------------------------------------------

#: A separator must reach this precision to be reported as a leak candidate.
PRECISION_THRESHOLD = 0.90
#: ...and must recover at least this fraction of the class. A predicate that
#: finds one planted row out of forty is not a leak, it is a coincidence.
RECALL_THRESHOLD = 0.50
#: Family-wise error rate, Bonferroni-corrected WITHIN FAMILY (singles
#: corrected over singles, pairs over pairs) rather than over the whole search.
#:
#: ## Why significance does not gate the build, and effect size does
#:
#: Measured on the frozen set: `description == 'Settlement processing fee'`
#: reaches precision 1.000 at recall 0.500 over the six minted calibration
#: rows -- p = 8.79e-06 against a Bonferroni alpha of 3.79e-06 over the 2,641
#: single-column hypotheses. It MISSES significance by a factor of 2.3.
#:
#: It is also a leak that anyone can exploit in ten seconds: grep that string
#: and get three minted rows with no false positives. A six-row class in a
#: 240-row file simply cannot be certified by a thousands-of-hypotheses
#: search; that is a statement about POWER, not about the row being clean.
#:
#: The costs are asymmetric. A false alarm costs one regeneration. A missed
#: leak costs the submission. So the build gates on EFFECT SIZE -- precision
#: and recall -- and reports significance beside it as `certified`, together
#: with whether the class was even powered enough to be certifiable.
ALPHA = 0.01
#: A class smaller than this cannot be audited meaningfully -- with 2 positives
#: no p-value can clear correction. Reported as UNTESTABLE, never as PASS.
MIN_CLASS_SIZE = 3
#: KS statistic above which a numeric column's distribution is called out.
KS_THRESHOLD = 0.60
#: Predicates kept per column when building pairs; keeps the pair search
#: quadratic in a small number rather than in the full predicate space.
PAIR_TOP_K = 6
#: Minimum lift over the base rate. Precision alone is meaningless when the
#: class is most of the file: at 0% attestation coverage EVERY settled row is
#: unattested, so `settled == True` reaches precision 1.000 / recall 1.000 at
#: lift 1.2. That is not a leak, it is the definition of the axis point.
MIN_LIFT = 2.0
#: A class covering more than this share of its table cannot be meaningfully
#: separated FROM the table -- it IS the table. Reported as degenerate, never
#: as clean and never as a leak.
MAX_BASE_RATE = 0.5


# --------------------------------------------------------------------------
# statistics -- exact, no scipy dependency for the tail we need
# --------------------------------------------------------------------------


def hypergeom_sf(k: int, population: int, successes: int, draws: int) -> float:
    """P(X >= k) for a hypergeometric draw. Exact, integer-arithmetic.

    *population* items, *successes* of them planted, *draws* selected by the
    predicate, *k* of the draws planted. Answers: if this predicate had no
    relationship to the class, how often would it capture at least this many?
    """
    if draws <= 0 or successes <= 0:
        return 1.0
    total = math.comb(population, draws)
    if total == 0:
        return 1.0
    upper = min(draws, successes)
    tail = sum(math.comb(successes, i) * math.comb(population - successes, draws - i)
               for i in range(k, upper + 1)
               if 0 <= draws - i <= population - successes)
    return tail / total


def ks_two_sample(a: Sequence[float], b: Sequence[float]) -> float:
    """Two-sample Kolmogorov-Smirnov statistic. No p-value: the statistic is
    reported alongside the hypergeometric evidence, not instead of it."""
    if not a or not b:
        return 0.0
    values = sorted(set(a) | set(b))
    sa, sb = sorted(a), sorted(b)

    def cdf(sample: Sequence[float], x: float) -> float:
        low, high = 0, len(sample)
        while low < high:
            mid = (low + high) // 2
            if sample[mid] <= x:
                low = mid + 1
            else:
                high = mid
        return low / len(sample)

    return max(abs(cdf(sa, v) - cdf(sb, v)) for v in values)


# --------------------------------------------------------------------------
# the tables under audit
# --------------------------------------------------------------------------


@dataclass
class Table:
    """A solver-visible file, as units with named columns.

    `key` is the identity a planted class is expressed in (entity_id for recon
    rows, invoice_no for ERP, the line index for the bank statement).
    """

    name: str
    key: str
    units: list[dict[str, Any]]

    @property
    def keys(self) -> list[str]:
        return [str(u[self.key]) for u in self.units]

    def columns(self) -> list[str]:
        seen: dict[str, None] = {}
        for unit in self.units:
            for column in unit:
                seen.setdefault(column, None)
        return list(seen)


def load_tables(data_dir: Path) -> dict[str, Table]:
    """Load ONLY the solver-visible files. The answer key is not opened here."""
    tables: dict[str, Table] = {}

    rows = json.loads((data_dir / "recon_combined.json").read_text())["items"]
    for position, row in enumerate(rows):
        row["_file_position"] = position
    tables["recon"] = Table("recon", "entity_id", rows)

    def csv_table(name: str, filename: str, key: str) -> None:
        path = data_dir / filename
        if not path.exists():
            return
        with path.open(newline="") as handle:
            units = list(csv.DictReader(handle))
        for position, unit in enumerate(units):
            unit["_file_position"] = position
        if key == "_file_position":
            for unit in units:
                unit["_index"] = unit["_file_position"]
        tables[name] = Table(name, key, units)

    csv_table("settlement_report", "settlement_report.csv", "settlement_id")
    csv_table("erp", "erp_orders.csv", "invoice_no")
    csv_table("gstr2b", "gstr2b.csv", "invoice_no")
    csv_table("bank", "bank_statement.csv", "_file_position")
    return tables


# --------------------------------------------------------------------------
# predicates
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Predicate:
    """One candidate separator, described well enough to be reproduced by hand."""

    description: str
    column: str
    test: Callable[[dict], bool] = field(compare=False, repr=False)

    def support(self, table: Table) -> set[str]:
        out = set()
        for unit in table.units:
            try:
                if self.test(unit):
                    out.add(str(unit[table.key]))
            except (TypeError, ValueError, KeyError):
                continue
        return out


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _tokens(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    out: list[str] = []
    for chunk in value.replace("/", " ").replace("-", " ").replace("_", " ").split():
        if 3 <= len(chunk) <= 40:
            out.append(chunk.lower())
    return out


def single_column_predicates(table: Table, max_levels: int = 40) -> list[Predicate]:
    """Every value-, null-, threshold- and token-predicate the columns admit.

    Deliberately generous: the point is to search the space, not to test the
    handful of predicates whose leak we already closed. `_file_position` is
    excluded here and handled by the ordering family instead.
    """
    predicates: list[Predicate] = []
    for column in table.columns():
        if column.startswith("_"):
            continue
        values = [unit.get(column) for unit in table.units]

        present = sum(1 for v in values if v is not None and v != "")
        if 0 < present < len(values):
            predicates.append(Predicate(f"{column} IS NULL/blank", column,
                                        lambda u, c=column: u.get(c) in (None, "")))
            predicates.append(Predicate(f"{column} IS NOT NULL/blank", column,
                                        lambda u, c=column: u.get(c) not in (None, "")))

        # key ABSENT is not the same as key present-and-null (credit_type)
        absent = sum(1 for unit in table.units if column not in unit)
        if 0 < absent < len(table.units):
            predicates.append(Predicate(f"{column} KEY ABSENT", column,
                                        lambda u, c=column: c not in u))

        hashables = [v for v in values if isinstance(v, (str, int, float, bool))]
        levels = Counter(hashables)
        if 0 < len(levels) <= max_levels:
            for level, _count in levels.most_common(max_levels):
                predicates.append(
                    Predicate(f"{column} == {level!r}", column,
                              lambda u, c=column, lv=level: u.get(c) == lv))

        numbers = sorted({n for n in (_as_number(v) for v in values) if n is not None})
        if len(numbers) >= 4:
            # every observed value is a candidate threshold; a leak does not
            # politely land on a round number
            for threshold in numbers:
                predicates.append(
                    Predicate(f"{column} >= {threshold:g}", column,
                              lambda u, c=column, t=threshold:
                              (_as_number(u.get(c)) is not None
                               and _as_number(u.get(c)) >= t)))
                predicates.append(
                    Predicate(f"{column} <= {threshold:g}", column,
                              lambda u, c=column, t=threshold:
                              (_as_number(u.get(c)) is not None
                               and _as_number(u.get(c)) <= t)))

        vocabulary = Counter(token for v in values for token in _tokens(v))
        for token, _count in vocabulary.most_common(max_levels):
            predicates.append(
                Predicate(f"{column} CONTAINS {token!r}", column,
                          lambda u, c=column, tk=token:
                          isinstance(u.get(c), str) and tk in u[c].lower()))

        # `notes` is polymorphic; a (key, value) pair leaked once already, so
        # both keys and pairs are enumerated as predicates in their own right
        if any(isinstance(v, dict) for v in values):
            pairs = Counter()
            for v in values:
                if isinstance(v, dict):
                    for k, item in v.items():
                        pairs[(k, str(item))] += 1
                        pairs[(k, "*")] += 1
            for (k, item), _count in pairs.most_common(max_levels * 2):
                predicates.append(
                    Predicate(f"{column}[{k!r}] == {item!r}", column,
                              lambda u, c=column, kk=k, vv=item:
                              isinstance(u.get(c), dict) and kk in u[c]
                              and (vv == "*" or str(u[c][kk]) == vv)))
    return predicates


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    family: str
    table: str
    description: str
    precision: float
    recall: float
    support: int
    class_size: int
    population: int
    p_value: float
    significant: bool
    #: p <= the within-family Bonferroni alpha. Reported, NOT gated: see ALPHA.
    certified: bool = False
    #: the smallest p-value this class size could ever attain. When it exceeds
    #: alpha the class is UNDERPOWERED and the audit cannot certify it clean --
    #: which is different from finding it clean, and is reported as such.
    min_attainable_p: float = 1.0
    #: the corrected alpha this finding was scored against
    alpha: float = ALPHA
    detail: str = ""

    @property
    def base_rate(self) -> float:
        return self.class_size / self.population if self.population else 0.0

    @property
    def lift(self) -> float:
        return self.precision / self.base_rate if self.base_rate else 0.0

    @property
    def underpowered(self) -> bool:
        return self.min_attainable_p > 0 and not self.certified \
            and self.significant

    def line(self) -> str:
        mark = "LEAK" if self.significant else "    "
        seal = "certified" if self.certified else "uncertified"
        return (f"{self.family:<14} {self.table:<7} prec={self.precision:.3f} "
                f"rec={self.recall:.3f} lift={self.lift:5.1f}x "
                f"p={self.p_value:.2e} {mark} [{seal}]  {self.description}")


@dataclass
class ClassAudit:
    name: str
    table: str
    class_size: int
    population: int
    testable: bool
    findings: list[Finding] = field(default_factory=list)
    note: str = ""

    @property
    def strongest(self) -> "Finding | None":
        significant = [f for f in self.findings if f.significant]
        pool = significant or self.findings
        if not pool:
            return None
        return max(pool, key=lambda f: (f.significant, f.precision * f.recall,
                                        -f.p_value))

    @property
    def underpowered(self) -> bool:
        """No finding on this class could EVER be certified.

        `min_attainable_p` is the p-value of a perfect separator at this class
        size and population. When even that cannot clear the corrected alpha,
        the class is structurally uncertifiable and its findings cannot be
        trusted in either direction -- so it is reported UNDERPOWERED rather
        than gated.

        This is the rule that distinguishes two cases that look alike:

          frozen D5   6 minted rows in 240   min attainable p = 4e-12  POWERED
                      -> a precision-1.000 separator is a real leak, gated.
          A20_B75 d04 3 settlements in 12    min attainable p = 4.5e-3 UNDER-
                      -> a threshold catching 2 of 3 on a continuous amount is
                         a rule fitted to noise. Amounts are drawn
                         independently of attestation; there is no mechanism.

        Without it the audit would either miss D5 or block the build on
        coincidences, and there is no single threshold that does both.
        """
        return all(f.min_attainable_p > f.alpha for f in self.findings) \
            if self.findings else False

    @property
    def failed(self) -> bool:
        return (not self.underpowered
                and any(f.significant for f in self.findings))


# --------------------------------------------------------------------------
# the five families
# --------------------------------------------------------------------------


def _score(family: str, table: Table, description: str, support: set[str],
           positives: set[str], hypotheses: int, detail: str = "") -> Finding | None:
    population = len(table.units)
    if not support or len(support) == population:
        return None
    hits = len(support & positives)
    if not hits:
        return None
    precision = hits / len(support)
    recall = hits / len(positives)
    p_value = hypergeom_sf(hits, population, len(positives), len(support))
    alpha = ALPHA / max(hypotheses, 1)
    # EFFECT SIZE gates the build; significance is reported beside it.
    significant = (precision >= PRECISION_THRESHOLD
                   and recall >= RECALL_THRESHOLD)
    base_rate = len(positives) / population if population else 0.0
    if base_rate > MAX_BASE_RATE or (precision / base_rate if base_rate else 0) < MIN_LIFT:
        significant = False
    floor = 1.0 / math.comb(population, len(positives)) \
        if population >= len(positives) else 1.0
    return Finding(family=family, table=table.name, description=description,
                   precision=precision, recall=recall, support=len(support),
                   class_size=len(positives), population=population,
                   p_value=p_value, significant=significant,
                   certified=p_value <= alpha, min_attainable_p=floor,
                   alpha=alpha, detail=detail)


def audit_single_and_pairs(table: Table, positives: set[str]) -> list[Finding]:
    predicates = single_column_predicates(table)
    supports = [(p, p.support(table)) for p in predicates]
    supports = [(p, s) for p, s in supports if s and len(s) < len(table.units)]

    # hypothesis count is the whole search space, singles plus the pairs we
    # will actually evaluate -- correction must reflect what was looked at
    by_column: dict[str, list[tuple[Predicate, set[str]]]] = defaultdict(list)
    for predicate, support in supports:
        by_column[predicate.column].append((predicate, support))
    trimmed: dict[str, list[tuple[Predicate, set[str]]]] = {}
    for column, items in by_column.items():
        items.sort(key=lambda ps: -(len(ps[1] & positives) / max(len(ps[1]), 1)))
        trimmed[column] = items[:PAIR_TOP_K]
    columns = sorted(trimmed)
    pair_count = sum(len(trimmed[a]) * len(trimmed[b])
                     for i, a in enumerate(columns) for b in columns[i + 1:])

    findings: list[Finding] = []
    for predicate, support in supports:
        finding = _score("single_column", table, predicate.description,
                         support, positives, len(supports))
        if finding:
            findings.append(finding)

    for i, a in enumerate(columns):
        for b in columns[i + 1:]:
            for pa, sa in trimmed[a]:
                for pb, sb in trimmed[b]:
                    both = sa & sb
                    finding = _score("column_pair", table,
                                     f"({pa.description}) AND ({pb.description})",
                                     both, positives, max(pair_count, 1))
                    if finding:
                        findings.append(finding)
    return findings


def audit_ordering(table: Table, positives: set[str]) -> list[Finding]:
    """File position and any field's ordinal rank.

    The D6 shape is exactly this: the six orphan invoices are NOT clustered by
    file position -- they sit at 45, 65, 74, 102, 143 and 161 of 184 -- but
    they hold the six highest invoice NUMBERS. A position-only check passes
    that dataset. A rank check does not.
    """
    findings: list[Finding] = []
    population = len(table.units)
    size = len(positives)
    if not size:
        return findings

    rankable: list[tuple[str, list[tuple[float, str]]]] = [
        ("_file_position", [(float(u["_file_position"]), str(u[table.key]))
                            for u in table.units])
    ]
    for column in table.columns():
        if column.startswith("_"):
            continue
        pairs = []
        for unit in table.units:
            number = _as_number(unit.get(column))
            if number is None:
                number = _trailing_number(unit.get(column))
            if number is not None:
                pairs.append((number, str(unit[table.key])))
        if len(pairs) >= population * 0.8 and len({p[0] for p in pairs}) > 2:
            rankable.append((column, pairs))

    hypotheses = len(rankable) * 2
    for column, pairs in rankable:
        for direction, label in ((1, "lowest"), (-1, "highest")):
            ordered = [key for _n, key in sorted(pairs, key=lambda p: (direction * p[0], p[1]))]
            window = set(ordered[:size])
            finding = _score("ordering", table,
                             f"the {size} {label} values of {column}",
                             window, positives, hypotheses,
                             detail=f"contiguous rank window, ordered by {column}")
            if finding:
                findings.append(finding)
    return findings


def _trailing_number(value: Any) -> float | None:
    """The trailing integer of a string id -- `ACM/26-27/1179` -> 1179."""
    if not isinstance(value, str):
        return None
    digits = ""
    for character in reversed(value):
        if character.isdigit():
            digits = character + digits
        elif digits:
            break
        else:
            continue
    return float(digits) if digits else None


def audit_distributional(table: Table, positives: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for column in table.columns():
        if column.startswith("_"):
            continue
        planted, organic = [], []
        for unit in table.units:
            number = _as_number(unit.get(column))
            if number is None:
                continue
            (planted if str(unit[table.key]) in positives else organic).append(number)
        if len(planted) < MIN_CLASS_SIZE or len(organic) < MIN_CLASS_SIZE:
            continue
        statistic = ks_two_sample(planted, organic)
        if statistic >= KS_THRESHOLD:
            findings.append(Finding(
                family="distributional", table=table.name,
                description=f"KS(planted, organic) on {column}",
                precision=0.0, recall=0.0, support=len(planted),
                class_size=len(positives), population=len(table.units),
                p_value=float("nan"), significant=False,
                detail=(f"D={statistic:.3f} over {len(planted)} planted vs "
                        f"{len(organic)} organic -- reported, not gated: a "
                        "distribution shift is a lead, not a separator")))
    return findings


# --------------------------------------------------------------------------
# derivability -- is any field a function of any other?
# --------------------------------------------------------------------------


@dataclass
class Derivation:
    left: str
    right: str
    rule: str
    coverage: float
    examples: tuple[str, ...] = ()

    def line(self) -> str:
        return (f"derivability   {self.left} = {self.rule} "
                f"[{self.coverage:.1%} of rows]"
                + (f"  e.g. {self.examples[0]}" if self.examples else ""))


def audit_derivability(units: Sequence[dict], columns: Sequence[str],
                       min_coverage: float = 0.95) -> list[Derivation]:
    """Is field X a function -- string, arithmetic or ordering -- of others?

    Three shapes, each of which has actually occurred in this project's data:

    * **concatenation / containment** -- the frozen `settlement_utr` is
      ``str(settled_at) + settlement_id[-6:]``, and the bank narration embeds
      the UTR verbatim. Found by splitting X at every position and asking
      whether each half is a substring of some other field.
    * **arithmetic** -- ``credit == amount - fee``. Legitimate here, and
      reported anyway: the audit's job is to state what is recoverable, not to
      decide which recoveries are acceptable.
    * **functional dependence** -- ``settled_at`` determines ``settlement_id``
      1:1, so a withheld column is re-supplied by a column that was not.
    """
    derivations: list[Derivation] = []
    usable = [c for c in columns if not c.startswith("_")]

    def string_of(unit: dict, column: str) -> str | None:
        value = unit.get(column)
        if value is None or isinstance(value, (dict, list, bool)):
            return None
        text = str(value)
        return text if len(text) >= 4 else None

    # --- string concatenation / containment --------------------------------
    for left in usable:
        rows = [u for u in units if string_of(u, left)]
        if len(rows) < max(MIN_CLASS_SIZE, len(units) * 0.05):
            continue
        for right in usable:
            if right == left:
                continue
            whole = sum(1 for u in rows
                        if string_of(u, right) and string_of(u, right) in string_of(u, left))
            if whole / len(rows) >= min_coverage:
                example = next(f"{string_of(u, right)} inside {string_of(u, left)}"
                               for u in rows if string_of(u, right)
                               and string_of(u, right) in string_of(u, left))
                derivations.append(Derivation(
                    left, right, f"contains {right} verbatim",
                    whole / len(rows), (example,)))
        # two-field concatenation, with a suffix/prefix slice on the second
        for a in usable:
            for b in usable:
                if a in (left,) or b in (left,) or a == b:
                    continue
                hits, example = 0, None
                for unit in rows:
                    target, sa, sb = string_of(unit, left), string_of(unit, a), string_of(unit, b)
                    if not (target and sa and sb):
                        continue
                    if not target.startswith(sa):
                        continue
                    tail = target[len(sa):]
                    if tail and (tail in sb):
                        hits += 1
                        example = example or f"{target} = {a}({sa}) + {b}[..{tail}]"
                if hits / len(rows) >= min_coverage:
                    derivations.append(Derivation(
                        left, f"{a}+{b}", f"{a} concatenated with a slice of {b}",
                        hits / len(rows), (example,) if example else ()))

    # --- arithmetic --------------------------------------------------------
    numeric = [c for c in usable
               if sum(1 for u in units if _as_number(u.get(c)) is not None)
               >= len(units) * 0.8]
    for target in numeric:
        for a in numeric:
            for b in numeric:
                if len({target, a, b}) < 3:
                    continue
                for symbol, operation in (("+", lambda x, y: x + y),
                                          ("-", lambda x, y: x - y)):
                    hits = total = 0
                    for unit in units:
                        t, x, y = (_as_number(unit.get(target)),
                                   _as_number(unit.get(a)), _as_number(unit.get(b)))
                        if None in (t, x, y):
                            continue
                        total += 1
                        hits += abs(t - operation(x, y)) < 1e-9
                    if total and hits / total >= min_coverage:
                        derivations.append(Derivation(
                            target, f"{a}{symbol}{b}", f"{a} {symbol} {b}",
                            hits / total))

    # --- functional dependence (X determines Y) ----------------------------
    for left in usable:
        mapping: dict[Any, set[Any]] = defaultdict(set)
        for unit in units:
            value = unit.get(left)
            if value is None or isinstance(value, (dict, list)):
                continue
            for right in usable:
                if right == left:
                    continue
                other = unit.get(right)
                if other is not None and not isinstance(other, (dict, list)):
                    mapping[(left, right, value)].add(other)
        for right in usable:
            if right == left:
                continue
            groups = {k[2]: v for k, v in mapping.items() if k[1] == right}
            if len(groups) < MIN_CLASS_SIZE:
                continue
            # A near-unique determinant determines EVERYTHING trivially --
            # `entity_id` is a primary key, so "card_network is a function of
            # entity_id" is true of any table and says nothing. A functional
            # dependence is only informative when the determinant is
            # LOW-cardinality relative to the rows it covers.
            covered = sum(len(v) for v in groups.values())
            if len(groups) > 0.3 * max(covered, 1):
                continue
            if all(len(v) == 1 for v in groups.values()) and len(groups) < len(units):
                derivations.append(Derivation(
                    right, left, f"a function of {left} ({len(groups)} distinct values)",
                    1.0))
    return _dedupe_derivations(derivations)


def _dedupe_derivations(items: list[Derivation]) -> list[Derivation]:
    seen: set[tuple[str, str, str]] = set()
    out = []
    for item in sorted(items, key=lambda d: (-d.coverage, d.left, d.right)):
        key = (item.left, item.right, item.rule)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --------------------------------------------------------------------------
# class efficacy -- does a planted class do what it claims?
# --------------------------------------------------------------------------


@dataclass
class Efficacy:
    """A planted class checked against its own stated purpose.

    Not every defect is a leak. **D7 is the opposite of a leak**: the frozen
    `c15_same_day_same_amount_decoy` class is perfectly well hidden and simply
    does not work. It equalises the GROSS `amount` across a pair, but
    settlement arithmetic runs on `credit = amount - fee`, and the two decoys
    sit in different MDR tiers -- so their credits differ and no ambiguity is
    created at all.

    A separator search cannot find that, because there is nothing to find. It
    needs its own question: *did the class achieve the property it exists for?*
    """

    name: str
    claim: str
    achieved: int
    attempted: int
    detail: str = ""

    @property
    def effective(self) -> bool:
        return self.attempted > 0 and self.achieved == self.attempted

    def line(self) -> str:
        flag = "ok  " if self.effective else "INEFFECTIVE"
        return (f"{flag} {self.name:<34} {self.achieved}/{self.attempted}  "
                f"{self.claim}" + (f"  -- {self.detail}" if self.detail else ""))


def audit_credit_collisions(rows: Sequence[dict], pairs: Sequence[Sequence[str]],
                            name: str, expected_delta: int = 0) -> Efficacy:
    """Do the pairs collide on CREDIT, which is what the arithmetic runs on?"""
    by_id = {row["entity_id"]: row for row in rows}
    achieved = 0
    deltas: list[int] = []
    for pair in pairs:
        if len(pair) != 2 or not all(p in by_id for p in pair):
            continue
        left, right = (by_id[pair[0]], by_id[pair[1]])
        delta = left.get("credit", 0) - right.get("credit", 0)
        deltas.append(delta)
        achieved += abs(delta) == expected_delta
    return Efficacy(
        name=name,
        claim=(f"pairs collide on `credit` (delta {expected_delta})"
               if expected_delta == 0 else
               f"pairs differ on `credit` by exactly {expected_delta} paise"),
        achieved=achieved, attempted=len(deltas),
        detail=f"observed credit deltas {deltas[:6]}")


def audit_incidental_collisions(rows: Sequence[dict]) -> Efficacy:
    """How many credit collisions happen by ACCIDENT?

    The number that decides whether a decoy class contributes anything. On the
    frozen set, 4 pairs of payments share a credit and only one of them is a
    planted decoy -- so the class's single success is indistinguishable from
    the three accidents beside it.
    """
    seen: dict[int, list[str]] = {}
    for row in rows:
        if row.get("type") == "payment" and row.get("credit"):
            seen.setdefault(row["credit"], []).append(row["entity_id"])
    collisions = {value: ids for value, ids in seen.items() if len(ids) > 1}
    return Efficacy(
        name="incidental_credit_collisions", claim="baseline, for comparison",
        achieved=len(collisions), attempted=len(collisions),
        detail=f"{len(collisions)} credit values shared by 2+ payments")


# --------------------------------------------------------------------------
# bank independence -- the D4 check, stated as its own assertion
# --------------------------------------------------------------------------


@dataclass
class BankIndependenceReport:
    recoverable_fields: list[str]
    posting_lag_days: dict[int, int]
    reference_derivable: list[str]
    narration_embeds_reference: int
    bank_lines: int
    #: reference ordering vs settlement chronology
    reference_is_dense_sequence: bool
    #: Whether the posting-lag test could be evaluated at all. At the
    #: PSP-absence axis points the recon feed carries no `settled_at`, so there
    #: is no settlement date to measure a lag AGAINST. The distribution then
    #: comes out constant for the same reason a coin never flipped comes out
    #: constant, and reading that as "the bank has no clock of its own" would
    #: be this audit publishing a verdict on an unmeasured quantity -- the
    #: exact error class it exists to find.
    posting_lag_measurable: bool = True

    @property
    def independent(self) -> bool:
        """The bank is independent when nothing on its lines is COMPUTED from
        ledger state.

        `narration_embeds_reference` is deliberately NOT a condition: a bank
        putting its OWN reference in its OWN narration is a bank statement. It
        is only a leak when that reference is itself derivable, which
        `reference_derivable` covers.
        """
        return (not self.recoverable_fields
                and not self.reference_derivable
                and (len(self.posting_lag_days) > 1
                     or not self.posting_lag_measurable)
                and not self.reference_is_dense_sequence)

    def lines(self) -> list[str]:
        out = [f"bank lines: {self.bank_lines}",
               (f"posting lag (days): NOT MEASURABLE -- this feed carries no "
                f"settled_at, so there is no settlement date to measure a lag "
                f"against. Excluded from the verdict rather than counted as "
                f"constant."
                if not self.posting_lag_measurable else
                f"posting lag (days) distribution: {self.posting_lag_days}"
                + ("   <-- CONSTANT: the bank has no clock of its own"
                   if len(self.posting_lag_days) <= 1 else "")),
               f"narrations embedding their own reference verbatim: "
               f"{self.narration_embeds_reference}/{self.bank_lines}"
               "   (not a leak by itself -- see `reference_derivable`)"]
        if self.recoverable_fields:
            out.append("LEDGER FIELDS RECOVERABLE FROM THE BANK FILE: "
                       + ", ".join(self.recoverable_fields))
        if self.reference_derivable:
            out.append("BANK REFERENCE IS DERIVABLE: "
                       + "; ".join(self.reference_derivable))
        if self.reference_is_dense_sequence:
            out.append("bank references form a dense gapless sequence -- a real "
                       "bank counter serves other customers and has gaps")
        out.append(f"VERDICT: bank is {'INDEPENDENT' if self.independent else 'NOT INDEPENDENT'}")
        return out


#: Ledger columns whose appearance in the bank file is NOT a leak.
#:
#: `credit`/`debit`/`amount` -- the credit is the credit. This MUST leak; it is
#: the join evidence and the reason reconciliation is possible at all.
#:
#: `settlement_utr` -- the PSP genuinely knows the bank's reference, because it
#: initiated the transfer. The row carrying it is the PSP REPORTING the bank's
#: value, which is the legitimate attestation channel and the link the whole
#: corpus depends on. The DIRECTION is what matters: bank -> PSP is a report,
#: PSP -> bank is a fabrication. So the question is never "does the reference
#: appear in both files" (it must) but "is the reference RECONSTRUCTIBLE from
#: ledger fields alone" -- which is `reference_derivable`, and which is exactly
#: what D4 is.
PERMITTED_SHARED_COLUMNS = {"credit", "debit", "amount", "settlement_utr"}


def audit_bank_independence(data_dir: Path) -> BankIndependenceReport:
    """Prove -- or refute -- that no ledger field is recoverable from the bank file.

    The legitimate shared signal is the AMOUNT and only the amount: the bank
    credited what the PSP paid, and a reconciliation engine that could not use
    the amount would have nothing to work with. Everything else on the bank
    line must be the bank's own.
    """
    rows = json.loads((data_dir / "recon_combined.json").read_text())["items"]
    with (data_dir / "bank_statement.csv").open(newline="") as handle:
        bank = list(csv.DictReader(handle))

    reference_column = "utr" if bank and "utr" in bank[0] else "bank_reference"
    date_column = "date" if bank and "date" in bank[0] else "value_date"

    ledger_values: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for column, value in row.items():
            if column in PERMITTED_SHARED_COLUMNS:
                continue
            if isinstance(value, (str, int)) and not isinstance(value, bool) \
                    and len(str(value)) >= 6:
                ledger_values[column].add(str(value))

    blob = " ".join(str(v) for line in bank for v in line.values())
    recoverable = sorted(column for column, values in ledger_values.items()
                         if sum(1 for v in values if v in blob) >= 2)

    embeds = sum(1 for line in bank
                 if line.get(reference_column)
                 and line[reference_column] in line.get("narration", ""))

    from datetime import date as _date, datetime as _datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    settled_dates: dict[str, _date] = {}
    for row in rows:
        if row.get("settled_at"):
            settled_dates.setdefault(
                str(row["settled_at"]),
                _datetime.fromtimestamp(row["settled_at"], ist).date())
    unique_settled = sorted(settled_dates.values())

    # Lag is measured SET-WISE, not positionally. A positional pairing assumes
    # bank line i is settlement i, which is exactly the bijection the corpus
    # breaks with foreign lines -- so pairing that way would report nonsense
    # (negative lags) on a correct file.
    #
    # The solver-visible question is: does every bank line land exactly on a
    # settlement date? If so the bank has no clock of its own and the value
    # date IS `settled_at`, handing back a withheld column.
    lags: Counter[int] = Counter()
    settled_set = set(unique_settled)
    for line in bank:
        try:
            posted = _date.fromisoformat(line[date_column])
        except (KeyError, ValueError):
            continue
        if posted in settled_set:
            lags[0] += 1
        else:
            nearer = [(posted - when).days for when in unique_settled
                      if 0 < (posted - when).days <= 7]
            # `min([])` raises, and it did: at the PSP-absence axis points the
            # recon feed carries no `settled_at` at all, so `unique_settled` is
            # empty and EVERY line takes this branch. A latent bug in a guard
            # that had never been reached, found by a dataset shape that had
            # never existed -- which is the argument for adding the shape.
            if nearer:
                lags[min(nearer)] += 1
            else:
                lags[-1] += 1          # unrelated to any settlement date

    derivable: list[str] = []
    references = [line.get(reference_column, "") for line in bank]
    for reference, settled in zip(references, [str(int(s.strftime("%s"))) for s in unique_settled]
                                  if unique_settled else []):
        pass
    settled_stamps = sorted(settled_dates)
    for reference, stamp in zip(references, settled_stamps):
        if reference and stamp and reference.startswith(stamp):
            derivable.append(f"{reference!r} starts with settled_at {stamp}")
    for reference in references:
        if not reference:
            continue
        for row in rows:
            sid = row.get("settlement_id")
            if sid and len(sid) >= 6 and sid[-6:] in reference:
                derivable.append(f"{reference!r} contains settlement_id[-6:] {sid[-6:]!r}")
                break

    digits = [int("".join(c for c in r if c.isdigit()) or -1) for r in references if r]
    dense = False
    if len(digits) >= 3 and all(d >= 0 for d in digits):
        ordered = sorted(digits)
        spans = [b - a for a, b in zip(ordered, ordered[1:])]
        dense = bool(spans) and all(s == 1 for s in spans)

    return BankIndependenceReport(
        recoverable_fields=recoverable,
        posting_lag_days=dict(sorted(lags.items())),
        reference_derivable=sorted(set(derivable))[:6],
        narration_embeds_reference=embeds,
        bank_lines=len(bank),
        reference_is_dense_sequence=dense,
        posting_lag_measurable=bool(unique_settled))


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


@dataclass
class AuditReport:
    data_dir: str
    classes: list[ClassAudit]
    derivations: list[Derivation]
    bank: BankIndependenceReport
    efficacy: list[Efficacy] = field(default_factory=list)

    @property
    def failed_classes(self) -> list[ClassAudit]:
        return [c for c in self.classes if c.failed]

    @property
    def ineffective(self) -> list[Efficacy]:
        return [item for item in self.efficacy
                if item.attempted and not item.effective
                and item.name != "incidental_credit_collisions"]

    @property
    def passed(self) -> bool:
        return (not self.failed_classes and self.bank.independent
                and not self.ineffective)

    def render(self) -> str:
        out = [f"# LEAKAGE AUDIT -- {self.data_dir}", "",
               f"thresholds: precision >= {PRECISION_THRESHOLD}, "
               f"recall >= {RECALL_THRESHOLD}, "
               f"Bonferroni-corrected alpha = {ALPHA} / hypotheses",
               "", "## Bank independence", ""]
        out += [f"    {line}" for line in self.bank.lines()]
        out += ["", "## Per-class strongest separator", ""]
        for audit in sorted(self.classes, key=lambda c: c.name):
            if not audit.testable:
                out.append(f"  {audit.name:<44} UNTESTABLE  "
                           f"(class size {audit.class_size} < {MIN_CLASS_SIZE}) "
                           f"{audit.note}")
                continue
            strongest = audit.strongest
            if audit.underpowered and strongest is not None:
                out.append(f"  {audit.name:<44} UNDERPOWERED  "
                           f"{strongest.line()}")
                out.append(f"  {'':<44}      (class size {audit.class_size} of "
                           f"{audit.population}: even a PERFECT separator "
                           f"could only reach p={strongest.min_attainable_p:.1e}, "
                           f"above alpha={strongest.alpha:.1e}. Not certifiable "
                           "clean OR leaking -- reported, not gated)")
                continue
            if strongest is None:
                out.append(f"  {audit.name:<44} clean  "
                           f"(n={audit.class_size}/{audit.population}, "
                           "no predicate reached the class)")
                continue
            flag = "LEAK" if strongest.significant else "ok  "
            out.append(f"  {audit.name:<44} {flag} {strongest.line()}")
            if strongest.significant and not strongest.certified:
                out.append(f"  {'':<44}      (not statistically certified at "
                           f"this class size -- alpha needs p <= "
                           f"{ALPHA / max(strongest.support, 1):.1e}; the "
                           "effect size gates the build, see ALPHA)")
        if self.efficacy:
            out += ["", "## Class efficacy -- did the class do what it claims?",
                    ""]
            out += [f"    {item.line()}" for item in self.efficacy]
        if self.derivations:
            out += ["", "## Derivable fields", ""]
            out += [f"    {d.line()}" for d in self.derivations[:40]]
        out += ["", f"## VERDICT: {'PASS' if self.passed else 'FAIL'}", ""]
        if self.failed_classes:
            out.append("classes with a significant separator: "
                       + ", ".join(c.name for c in self.failed_classes))
        if not self.bank.independent:
            out.append("bank statement is not an independent source")
        if self.ineffective:
            out.append("classes that do not achieve what they claim: "
                       + ", ".join(item.name for item in self.ineffective))
        return "\n".join(out)


def audit(data_dir: Path, classes: dict[str, dict]) -> AuditReport:
    """Run every family over every planted class.

    `classes` maps class name -> {"table": <table name>, "members": [keys]}.
    It comes from the dataset's ground truth, which is why the audit lives in
    `corpus/` and not in a solver package.
    """
    tables = load_tables(data_dir)
    audits: list[ClassAudit] = []
    for name, spec in sorted(classes.items()):
        table = tables.get(spec["table"])
        if table is None:
            continue
        positives = {str(m) for m in spec["members"]} & set(table.keys)
        if len(positives) < MIN_CLASS_SIZE:
            audits.append(ClassAudit(name=name, table=table.name,
                                     class_size=len(positives),
                                     population=len(table.units), testable=False,
                                     note=spec.get("note", "")))
            continue
        if len(positives) > MAX_BASE_RATE * len(table.units):
            audits.append(ClassAudit(
                name=name, table=table.name, class_size=len(positives),
                population=len(table.units), testable=False,
                note=f"DEGENERATE: the class is {len(positives)}/"
                     f"{len(table.units)} of the table, so it cannot be "
                     "separated FROM it -- it IS it"))
            continue
        findings = (audit_single_and_pairs(table, positives)
                    + audit_ordering(table, positives)
                    + audit_distributional(table, positives))
        audits.append(ClassAudit(name=name, table=table.name,
                                 class_size=len(positives),
                                 population=len(table.units), testable=True,
                                 findings=findings, note=spec.get("note", "")))

    recon = tables["recon"]
    derivations = audit_derivability(recon.units, recon.columns())

    efficacy: list[Efficacy] = []
    for name, spec in sorted(classes.items()):
        pairs = spec.get("pairs")
        if not pairs:
            continue
        if isinstance(pairs[0], dict):          # near-collision shape
            for delta in sorted({item["delta"] for item in pairs}):
                efficacy.append(audit_credit_collisions(
                    recon.units, [item["pair"] for item in pairs
                                  if item["delta"] == delta],
                    f"{name}[delta={delta}]", expected_delta=delta))
        else:
            efficacy.append(audit_credit_collisions(recon.units, pairs, name))
    if efficacy:
        efficacy.append(audit_incidental_collisions(recon.units))

    return AuditReport(data_dir=str(data_dir), classes=audits,
                       derivations=derivations, efficacy=efficacy,
                       bank=audit_bank_independence(data_dir))


def classes_from_ground_truth(truth: dict) -> dict[str, dict]:
    """Translate a corpus ground-truth key into audit class specs.

    Corpus keys carry `planted_classes: {name: {table, members, planted, ...}}`
    directly. The frozen key predates that shape, so `--validate-frozen`
    translates it in `validate_frozen` instead.
    """
    out: dict[str, dict] = {}
    for name, spec in truth.get("planted_classes", {}).items():
        if not spec.get("planted", True):
            continue
        out[name] = {"table": spec.get("table", "recon"),
                     "members": spec.get("members", []),
                     "pairs": spec.get("pairs"),
                     "note": spec.get("reason", "")}
    return out


# --------------------------------------------------------------------------
# validation against the frozen set -- must rediscover D4, D5, D6, D7
# --------------------------------------------------------------------------


def frozen_minted_rows() -> list[str]:
    """The rows the frozen CALIBRATION PLANTERS minted, derived exactly.

    The frozen ground-truth key names calibrated *batches*, not the rows that
    were minted into them, so the D5 class cannot be read off it. Deriving the
    class from the leak itself ("large debit adjustment, null dispute_id")
    would be circular -- it would assume the answer the audit is supposed to
    find.

    So the frozen generator is driven as a library at the frozen seed and the
    adjustment/refund id sets are diffed ACROSS the planter calls. Nothing
    under `engine/` is written or patched; this is the same
    import-as-a-library mechanism `holdout/generate_holdout.py` uses.
    """
    import random
    if str(ROOT / "engine") not in sys.path:
        sys.path.insert(0, str(ROOT / "engine"))
    import generator as G                       # the FROZEN generator
    from simulator import SimulatorConfig

    rng = random.Random(20260822)
    mk = G.make_id_factory(rng)
    config = SimulatorConfig(batch_times=[G.ts(d) for d in G.BATCH_DATES])
    payments, refunds, adjustments, *_ = G.build_ledger(rng, mk)
    before = {r.id for r in refunds} | {a.id for a in adjustments}
    G.plant_pressure(payments, refunds, adjustments, config, rng, mk,
                     G.PRESSURE_BATCHES)
    G.plant_ambiguity(payments, refunds, adjustments, config, rng, mk,
                      G.AMBIGUITY_BATCHES)
    after = {r.id for r in refunds} | {a.id for a in adjustments}
    return sorted(after - before)


def frozen_classes() -> dict[str, dict]:
    """The frozen set's planted classes, expressed for the audit.

    Built from `engine/ground_truth/ground_truth.json` by this function and
    nowhere else -- the audit itself never opens an answer key.
    """
    truth = json.loads((ROOT / "engine" / "ground_truth" / "ground_truth.json").read_text())
    rows = json.loads((ROOT / "engine" / "data" / "recon_combined.json").read_text())["items"]
    by_settlement: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.get("settlement_id"):
            by_settlement[row["settlement_id"]].append(row["entity_id"])

    ambiguous = [b["settlement_id"] for b in truth["batches"] if b["ambiguous"]]
    calibrated = [e["settlement_id"] for e in truth["planted_ambiguity"] if e["planted"]]
    calibrated += [e["settlement_id"] for e in truth["planted_balance_pressure"]
                   if e.get("planted")]

    classes: dict[str, dict] = {
        "D5_minted_calibration_rows": {
            "table": "recon", "members": frozen_minted_rows()},
        "D5_rows_of_ambiguous_batches": {
            "table": "recon",
            "members": [r for s in ambiguous for r in by_settlement[s]]},
        "D5_rows_of_calibrated_batches": {
            "table": "recon",
            "members": sorted({r for s in set(calibrated) for r in by_settlement[s]})},
        "D6_erp_orphan_invoices": {
            "table": "erp", "members": truth["erp_orphan_invoices"]},
        "D7_decoy_payments": {
            "table": "recon",
            "members": [pid for pair in truth["decoy_pairs"] for pid in pair],
            "pairs": [list(pair) for pair in truth["decoy_pairs"]]},
        "payments_missing_from_erp": {
            "table": "recon", "members": truth["payments_missing_from_erp"]},
        "itc_at_risk": {
            "table": "gstr2b",
            "members": [e["invoice_no"] if isinstance(e, dict) else e
                        for e in truth["itc_at_risk"]]},
    }
    return classes


#: What `--validate-frozen` must find. Each entry names the defect, the class
#: the audit must flag, and the family that must flag it. If the audit stops
#: finding any of these, the audit itself has regressed.
FROZEN_EXPECTATIONS = [
    ("D4", "bank independence", None,
     "the bank file must be reported NOT INDEPENDENT"),
    ("D5", "D5_minted_calibration_rows", None,
     "the MINTED rows must be separable from organic ones -- the amount column "
     "alone should do it, before any description string is read"),
    ("D6", "D6_erp_orphan_invoices", "ordering",
     "the orphan invoices must be found by invoice-number RANK; a file-position "
     "check passes this dataset, because they are interleaved by position"),
    ("D7", "efficacy:D7_decoy_payments", None,
     "the decoy class must be reported INEFFECTIVE: it equalises `amount`, but "
     "the arithmetic runs on `credit`, and the tiers differ"),
]


def validate_frozen() -> tuple[bool, str]:
    report = audit(ROOT / "engine" / "data", frozen_classes())
    lines = ["# LEAKAGE AUDIT VALIDATION -- against the FROZEN primary dataset",
             "",
             "The audit is run against the dataset whose four data defects are",
             "already known. It must rediscover them WITHOUT being told what to",
             "look for. An audit that cannot find a known leak is not evidence",
             "about the leaks nobody has found yet.",
             ""]
    by_name = {c.name: c for c in report.classes}
    all_ok = True
    for defect, target, family, requirement in FROZEN_EXPECTATIONS:
        if target == "bank independence":
            found = not report.bank.independent
            evidence = "; ".join(report.bank.lines()[1:4])
        elif target.startswith("efficacy:"):
            name = target.split(":", 1)[1]
            item = next((e for e in report.efficacy if e.name == name), None)
            found = item is not None and not item.effective
            evidence = item.line().strip() if item else "class not present"
        else:
            audit_result = by_name.get(target)
            hits = [f for f in (audit_result.findings if audit_result else [])
                    if f.significant and (family is None or f.family == family)]
            found = bool(hits)
            best = max(hits, key=lambda f: f.precision * f.recall) if hits else None
            evidence = best.line().strip() if best else "nothing found"
        all_ok &= found
        lines.append(f"## {defect} -- {'REDISCOVERED' if found else 'MISSED'}")
        lines.append(f"required: {requirement}")
        lines.append(f"found:    {evidence}")
        lines.append("")
    lines.append(f"## VALIDATION: {'PASS' if all_ok else 'FAIL'}")
    lines.append("")
    lines.append(report.render())
    return all_ok, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("data_dir", nargs="?", type=Path,
                        help="a corpus dataset directory (with ground_truth.json)")
    parser.add_argument("--all", action="store_true",
                        help="audit every corpus dataset; a dataset that fails "
                             "its own audit does not ship")
    parser.add_argument("--validate-frozen", action="store_true",
                        help="run against engine/data and assert D4-D7 are rediscovered")
    parser.add_argument("--out", type=Path, help="write the report here")
    parser.add_argument("--json", type=Path, help="also write findings as JSON")
    arguments = parser.parse_args()

    if arguments.validate_frozen:
        ok, text = validate_frozen()
        print(text)
        if arguments.out:
            arguments.out.write_text(text + "\n")
        return 0 if ok else 1

    if arguments.all:
        # Both families. `datasets_v2` is a SUPERSET generation at new seeds,
        # not a correction of `datasets`, and both are audited and both ship.
        datasets = [p for family in ("datasets", "datasets_v2")
                    if (ROOT / "corpus" / family).exists()
                    for p in sorted((ROOT / "corpus" / family).iterdir())
                    if (p / "ground_truth.json").exists()]
        failed: list[str] = []
        sections: list[str] = []
        for dataset in datasets:
            truth = json.loads((dataset / "ground_truth.json").read_text())
            report = audit(dataset, classes_from_ground_truth(truth))
            sections.append(report.render())
            status = "PASS" if report.passed else "FAIL"
            print(f"{dataset.parent.name}/{dataset.name:<22} {status}"
                  + ("" if report.passed else
                     "  " + ", ".join(c.name for c in report.failed_classes)
                     + ("" if report.bank.independent else " [bank]")))
            if not report.passed:
                failed.append(dataset.name)
        if arguments.out:
            arguments.out.write_text("\n\n".join(sections) + "\n")
        print(f"\n{len(datasets) - len(failed)}/{len(datasets)} datasets pass "
              "their own leak audit")
        return 1 if failed else 0

    if not arguments.data_dir:
        parser.error("give a dataset directory, --all, or --validate-frozen")
    truth = json.loads((arguments.data_dir / "ground_truth.json").read_text())
    report = audit(arguments.data_dir, classes_from_ground_truth(truth))
    text = report.render()
    print(text)
    if arguments.out:
        arguments.out.write_text(text + "\n")
    if arguments.json:
        arguments.json.write_text(json.dumps(
            {"classes": [asdict(c) for c in report.classes],
             "bank": asdict(report.bank)}, indent=1, default=str))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
