"""Result types for the cascade.

The central design constraint: **a confident single answer on an ambiguous
batch must be unrepresentable**, not merely discouraged.

That is why `Ambiguous` has no `decomposition` attribute. There is no field to
read, no flag to forget to check, and no attribute access that yields "the"
answer. A caller that wants an assignment must first narrow the union, and the
only value carrying an assignment is `Determinate`, which cannot be constructed
from more than one candidate.

Resolutions are produced exclusively by `resolve_from_candidates`, which
enumerates first and decides confidence from the count. There is no
pick-then-check path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class Decomposition:
    """One candidate explanation of a bank credit.

    `credit_ids` and `debit_ids` are sorted tuples so equality and hashing are
    order-independent and output is deterministic.
    """

    credit_ids: tuple[str, ...]
    debit_ids: tuple[str, ...]
    credit_total: int
    debit_total: int

    @property
    def net(self) -> int:
        return self.credit_total - self.debit_total

    @property
    def row_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.credit_ids + self.debit_ids))

    @staticmethod
    def build(rows_by_id: dict, ids: Iterable[str]) -> "Decomposition":
        credits, debits, credit_total, debit_total = [], [], 0, 0
        for row_id in sorted(ids):
            row = rows_by_id[row_id]
            if row["credit"]:
                credits.append(row_id)
                credit_total += row["credit"]
            if row["debit"]:
                debits.append(row_id)
                debit_total += row["debit"]
            if not row["credit"] and not row["debit"]:
                credits.append(row_id)          # a zero-value row still belongs
        return Decomposition(tuple(sorted(credits)), tuple(sorted(debits)),
                             credit_total, debit_total)


@dataclass(frozen=True, slots=True)
class BalanceProof:
    """Why a resolution is believed. Every determinate match carries one."""

    bank_amount: int
    credit_total: int
    debit_total: int
    residual: int
    tolerance: int

    @property
    def holds(self) -> bool:
        return abs(self.residual) <= self.tolerance

    def describe(self) -> str:
        return (f"credit {self.credit_total} - debit {self.debit_total} "
                f"= {self.credit_total - self.debit_total} vs bank "
                f"{self.bank_amount}; residual {self.residual} "
                f"(tolerance {self.tolerance})")


class BalanceViolation(AssertionError):
    """A determinate resolution whose arithmetic does not close.

    This is a BUG in the solver, surfaced loudly. It is deliberately not an
    exception type that Stage 4 can route away: routing it would hide a wrong
    answer behind a plausible-looking exception queue.
    """


@dataclass(frozen=True, slots=True)
class Determinate:
    """Exactly one decomposition explains this bank credit."""

    decomposition: Decomposition
    proof: BalanceProof
    method: str

    def __post_init__(self) -> None:
        if not self.proof.holds:
            raise BalanceViolation(
                f"determinate resolution does not close: {self.proof.describe()}")

    @property
    def is_confident(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class Ambiguous:
    """Two or more decompositions explain this bank credit equally well.

    Deliberately exposes NO single assignment. `candidates` is the complete
    enumeration unless `truncated` is set, in which case it is a SAMPLE and the
    batch is *more* ambiguous than the list suggests, never less.
    """

    candidates: tuple[Decomposition, ...]
    truncated: bool
    method: str
    enumeration_cap: int

    def __post_init__(self) -> None:
        if len(self.candidates) < 2:
            raise ValueError("Ambiguous requires at least two candidates")

    @property
    def is_confident(self) -> bool:
        return False

    @property
    def certain_rows(self) -> tuple[str, ...]:
        """Rows present in EVERY candidate.

        Ambiguity about which subset settled does not mean total ignorance: a
        row in every tying decomposition is in the batch whichever candidate is
        true. Safe to consume; the symmetric difference is not.

        Meaningless when `truncated` -- an unseen candidate could drop any of
        them -- so it is empty in that case rather than optimistic.
        """
        if self.truncated:
            return ()
        common = set(self.candidates[0].row_ids)
        for candidate in self.candidates[1:]:
            common &= set(candidate.row_ids)
        return tuple(sorted(common))

    @property
    def contested_rows(self) -> tuple[str, ...]:
        union: set[str] = set()
        for candidate in self.candidates:
            union |= set(candidate.row_ids)
        return tuple(sorted(union - set(self.certain_rows)))


@dataclass(frozen=True, slots=True)
class Unresolved:
    """No decomposition of the candidate pool explains this bank credit."""

    reason: str
    pool_size: int
    method: str
    nearest_residual: int | None = None

    @property
    def is_confident(self) -> bool:
        return False


Resolution = Determinate | Ambiguous | Unresolved


def resolve_from_candidates(
    candidates: Sequence[Decomposition],
    *,
    bank_amount: int,
    truncated: bool,
    method: str,
    pool_size: int,
    enumeration_cap: int,
    tolerance: int = 0,
) -> Resolution:
    """The ONLY way to build a Resolution.

    Enumerate first, then decide confidence from the count. A single candidate
    plus a truncation flag is still ambiguous -- truncation means enumeration
    stopped early, so "one found" is not "one exists".
    """
    unique = sorted({(c.credit_ids, c.debit_ids): c for c in candidates}.values(),
                    key=lambda c: c.row_ids)
    if not unique:
        return Unresolved(reason="no_subset_sums_to_bank_amount",
                          pool_size=pool_size, method=method)
    if len(unique) == 1 and not truncated:
        only = unique[0]
        proof = BalanceProof(bank_amount=bank_amount,
                             credit_total=only.credit_total,
                             debit_total=only.debit_total,
                             residual=only.net - bank_amount,
                             tolerance=tolerance)
        return Determinate(decomposition=only, proof=proof, method=method)
    if len(unique) == 1 and truncated:
        # Enumeration stopped before it could look for a second solution.
        # Reporting this as determinate would assert something never checked.
        return Unresolved(reason="enumeration_truncated_before_uniqueness_proven",
                          pool_size=pool_size, method=method)
    return Ambiguous(candidates=tuple(unique), truncated=truncated,
                     method=method, enumeration_cap=enumeration_cap)
