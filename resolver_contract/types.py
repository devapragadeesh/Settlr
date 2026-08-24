"""The resolver contract, as executable types.

This module is INTERFACE AND SEMANTICS ONLY. It contains no algorithm, no
solver, no matching logic, and it imports nothing from `matching/`, `engine/`
or `corpus/`. It is written and committed BEFORE any corpus data exists, so
the corpus cannot be shaped to an implementation and an implementation cannot
be shaped to the corpus.

The central claim it encodes:

    An assignment is a claim about the world, and a claim needs a warrant.
    There is no constructor here that produces an assignment without one.

Read `RESOLVER_CONTRACT.md` for the prose and the rejected alternatives. The
load-bearing mechanics are:

* `Evidence` carries `derived_from` -- the SOURCE SYSTEMS its content actually
  came from. Independence is computed over sources, never over kinds, because
  two evidence kinds are routinely two names for one source's assertion. That
  is the frozen dataset's D4 defect exactly, and it is why arithmetic closure
  computed over attestation-named rows carries `derived_from={PSP_LEDGER}` and
  corroborates nothing.
* `Evidence` also carries `attests_to` -- whether it speaks to a credit's
  EXISTENCE, to its COMPOSITION, or is a CONSEQUENCE check on someone else's
  composition claim. A bank knows what it paid; it never knows which of the
  merchant's rows it paid for. Counting a bank reference as corroboration of a
  composition would certify a composition on existence evidence.
* `Verified.__post_init__` raises unless a composition was CLAIMED by one
  source and a falsifiable CONSEQUENCE of that claim was confirmed by an
  independent one. It also demands `rival_closure_count`, because a
  consequence confirmed by 400 rival compositions is weak corroboration and
  the report must be able to say so.
* `Reconstructed` demands cross-line exclusivity as well as unique closure.
  Per-credit uniqueness held at all three bank lines that produced the 50
  wrong rows -- uniqueness is not the property that was missing.
* `Ambiguous` has no `decomposition`, and reading one raises
  `UnrepresentableClaim` so the failure names the design intent.
* Abstention is not free. `DeterminedInstance` and `abstention_failures`
  define the subpopulation on which `Unresolved` is a defect, so a resolver
  cannot pass every soundness gate by answering nothing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Iterable, Sequence


# --------------------------------------------------------------------------
# Source systems -- the unit over which independence is determined
# --------------------------------------------------------------------------


class SourceSystem(enum.Enum):
    """Who asserted a thing.

    Independence is a property of SOURCES, not of evidence kinds. A settlement
    id and a UTR printed on a bank statement look like two facts, and they are
    two facts; they are only two SOURCES if the bank minted the UTR itself. In
    the frozen primary dataset it did not --
    ``utr == str(settled_at) + settlement_id[-6:]`` on 11 of 11 batches, and
    the narration embeds the UTR verbatim on 9 of 12 lines -- so both reduce to
    ``PSP_LEDGER`` and agreement between them is circular.
    """

    #: The PSP's recon feed: settlement_id, settled, settled_at,
    #: settlement_utr. One assertion written in four columns.
    PSP_LEDGER = "psp_ledger"
    #: The PSP's settlement report -- the same party as PSP_LEDGER and
    #: therefore NOT independent of it. Kept distinct because it is a distinct
    #: artefact that can be absent, stale or wrong on its own.
    PSP_SETTLEMENT_REPORT = "psp_settlement_report"
    #: The bank statement, IF its contents are minted bank-side. A bank
    #: statement that re-encodes the PSP's fields is not this source.
    BANK = "bank"
    #: The merchant's own sales ledger (ERP orders / invoices).
    MERCHANT_ERP = "merchant_erp"
    #: The tax authority's inward-supply statement (GSTR-2B).
    TAX_AUTHORITY = "tax_authority"
    #: The dispute record (issuer-originated).
    DISPUTE_RECORD = "dispute_record"
    #: Nothing external. Evidence computed purely from the resolver's own
    #: modelling. Never counts toward independence.
    RESOLVER_INTERNAL = "resolver_internal"


#: Sources that are the same PARTY and therefore never independent of one
#: another, whatever artefact they arrive on. Independence is counted over
#: these groups, not over the enum members.
SOURCE_PARTY = {
    SourceSystem.PSP_LEDGER: "psp",
    SourceSystem.PSP_SETTLEMENT_REPORT: "psp",
    SourceSystem.BANK: "bank",
    SourceSystem.MERCHANT_ERP: "merchant",
    SourceSystem.TAX_AUTHORITY: "tax_authority",
    SourceSystem.DISPUTE_RECORD: "issuer",
    SourceSystem.RESOLVER_INTERNAL: "resolver",
}

#: Parties that may count toward the two-independent-sources rule. A
#: resolver's own arithmetic is not a witness to anything.
NON_CORROBORATING_PARTIES = frozenset({"resolver"})


def parties(sources: Iterable[SourceSystem]) -> frozenset[str]:
    """Independent parties behind a set of sources."""
    return frozenset(SOURCE_PARTY[s] for s in sources) - NON_CORROBORATING_PARTIES


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class Attests(enum.Enum):
    """WHAT a piece of evidence is evidence OF. See contract sec 3.2.

    The distinction the previous engine did not draw, and the reason it could
    call a match "corroborated" when nothing had corroborated the composition.
    """

    #: Names which rows made up the credit. Only a party that saw the batch
    #: form can do this.
    COMPOSITION = "composition"
    #: Says a credit of this amount, on this date, under this reference,
    #: exists. Says NOTHING about which rows composed it.
    EXISTENCE = "existence"
    #: Confirms a falsifiable, checkable consequence of someone else's
    #: composition claim -- e.g. "the rows the PSP named sum to what the bank
    #: actually paid." This is real corroboration and it is weaker than
    #: witnessing the composition. How much weaker depends on how many rival
    #: compositions produce the same consequence, which is why
    #: `Verified.rival_closure_count` is mandatory.
    CONSEQUENCE = "consequence"
    #: Speaks to an individual row's reality, not to its batch membership.
    ROW_EXISTENCE = "row_existence"


class EvidenceKind(enum.Enum):
    """What kind of thing supports an assignment."""

    #: The PSP says these rows formed this batch. An assertion, not an
    #: observation. Strong, checkable, and routinely wrong in production --
    #: which is what `AttestationDiscrepancy` exists to say.
    ATTESTED_SETTLEMENT_ID = "attested_settlement_id"

    #: A reference the BANK minted for the credit it posted. Independent
    #: evidence only when the bank minted it (see `derived_from`), and
    #: evidence of EXISTENCE only (see `attests_to`).
    BANK_REFERENCE = "bank_reference"

    #: The bank's own value date. Weak alone; useful for contradiction -- a
    #: row created after the credit posted cannot be in it.
    BANK_VALUE_DATE = "bank_value_date"

    #: The rows named by some composition claim sum to the amount an
    #: independent party actually paid. A CONSEQUENCE check on that claim.
    ATTESTED_COMPOSITION_CLOSES = "attested_composition_closes"

    #: The selected rows sum to the target. A consistency check with no
    #: independent content whatsoever when the rows were chosen to make it
    #: true. Present so a resolver can record its own arithmetic honestly.
    ARITHMETIC_CLOSURE = "arithmetic_closure"

    #: Exactly one subset of the pool closes to the amount, established with
    #: NO objective filtering the candidate set.
    UNIQUE_CLOSURE_UNFILTERED = "unique_closure_unfiltered"

    #: That subset does not also close any OTHER unexplained credit in the
    #: window. Required by `Reconstructed`; see contract sec 4.3 and the
    #: 50-row identity failure it exists to prevent.
    CROSS_LINE_EXCLUSIVITY = "cross_line_exclusivity"

    #: order_id / invoice linkage into the merchant's books.
    ERP_IDENTIFIER = "erp_identifier"

    #: A GSTR-2B line ties to the fee column of the settlements it covers.
    GST_DOCUMENT = "gst_document"

    #: An issuer-originated dispute record explaining a hold or a clawback.
    DISPUTE_RECORD_LINK = "dispute_record_link"


#: Evidence kinds that are DERIVED -- computed by the resolver rather than
#: asserted by anyone. Their `derived_from` must name the sources whose content
#: they were computed over; they never introduce a new source.
DERIVED_KINDS = frozenset({
    EvidenceKind.ARITHMETIC_CLOSURE,
    EvidenceKind.UNIQUE_CLOSURE_UNFILTERED,
    EvidenceKind.CROSS_LINE_EXCLUSIVITY,
    EvidenceKind.ATTESTED_COMPOSITION_CLOSES,
})

#: The declared, FIXED semantics of every evidence kind. A resolver does not
#: get to decide what its evidence attests to -- that is the tautology the
#: contract exists to prevent. The oracle validates a resolver's `Evidence`
#: against this table and against the corpus provenance graph.
EVIDENCE_SEMANTICS: dict[EvidenceKind, Attests] = {
    EvidenceKind.ATTESTED_SETTLEMENT_ID: Attests.COMPOSITION,
    EvidenceKind.BANK_REFERENCE: Attests.EXISTENCE,
    EvidenceKind.BANK_VALUE_DATE: Attests.EXISTENCE,
    EvidenceKind.ATTESTED_COMPOSITION_CLOSES: Attests.CONSEQUENCE,
    EvidenceKind.ARITHMETIC_CLOSURE: Attests.CONSEQUENCE,
    EvidenceKind.UNIQUE_CLOSURE_UNFILTERED: Attests.COMPOSITION,
    EvidenceKind.CROSS_LINE_EXCLUSIVITY: Attests.COMPOSITION,
    EvidenceKind.ERP_IDENTIFIER: Attests.ROW_EXISTENCE,
    EvidenceKind.GST_DOCUMENT: Attests.ROW_EXISTENCE,
    EvidenceKind.DISPUTE_RECORD_LINK: Attests.ROW_EXISTENCE,
}


class ContractViolation(AssertionError):
    """A resolver produced an outcome the contract forbids.

    Deliberately an `AssertionError` subclass and deliberately NOT routable to
    an exception queue: routing it would hide an unwarranted claim behind a
    plausible-looking queue entry, which is the failure mode this contract
    exists to prevent.
    """


class UnrepresentableClaim(ContractViolation):
    """Code reached for an assignment an outcome cannot carry.

    The canonical case is `Ambiguous.decomposition`. The attribute is missing
    ON PURPOSE, and this exception says so at the point of use rather than
    letting it look like a typo.
    """


@dataclass(frozen=True, slots=True)
class Evidence:
    """One piece of support for a claim.

    `derived_from` is the load-bearing field: the set of source systems whose
    CONTENT this evidence actually carries -- not the set it is nominally
    about. Getting it wrong is how circular corroboration happens.
    """

    kind: EvidenceKind
    #: Sources whose content this evidence carries. For an assertion, the
    #: single system that made it. For DERIVED evidence, the union of the
    #: sources of whatever the computation ran over.
    derived_from: frozenset[SourceSystem]
    #: Human-readable statement of the specific fact, for the report.
    detail: str
    #: Row ids this evidence speaks about. Empty means "the whole bank line".
    supports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.derived_from:
            raise ContractViolation(
                f"{self.kind.value}: evidence must name at least one source it "
                "derives from; anonymous evidence is not evidence")
        if (self.kind is EvidenceKind.ATTESTED_SETTLEMENT_ID
                and parties(self.derived_from) != frozenset({"psp"})):
            raise ContractViolation(
                "an attestation derives from the PSP and nothing else")
        if (self.kind is EvidenceKind.BANK_REFERENCE
                and SourceSystem.BANK not in self.derived_from):
            raise ContractViolation(
                "bank-reference evidence must derive from the BANK; if the "
                "reference is computable from ledger fields it is not the "
                "bank's assertion (defect D4)")

    @property
    def attests_to(self) -> Attests:
        """FIXED by `EVIDENCE_SEMANTICS`. Not a resolver's choice."""
        return EVIDENCE_SEMANTICS[self.kind]

    @property
    def is_derived(self) -> bool:
        return self.kind in DERIVED_KINDS


def arithmetic_closure_over(
    row_sources: Iterable[SourceSystem], *, detail: str,
    supports: tuple[str, ...] = (),
    kind: EvidenceKind = EvidenceKind.ARITHMETIC_CLOSURE,
) -> Evidence:
    """Build closure evidence with honest provenance.

    Closure inherits the sources of the rows it closed over. If the attestation
    chose the rows, the closure derives from the PSP and adds no independent
    source -- it is a check on that attestation, exactly as contract sec 3.3
    requires. This helper exists so that fact is expressed by construction
    rather than remembered.

    Note what makes an attested composition's closure into CORROBORATION: not
    the arithmetic, but the fact that the TARGET came from the bank. Pass
    `SourceSystem.BANK` in `row_sources` only when the target is the bank's
    figure, and use `ATTESTED_COMPOSITION_CLOSES` for that case.
    """
    sources = frozenset(row_sources)
    if not sources:
        raise ContractViolation(
            "closure must name the sources of the rows it closed over")
    return Evidence(kind=kind, derived_from=sources, detail=detail,
                    supports=supports)


# --------------------------------------------------------------------------
# Independence and contradiction
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndependenceDetermination:
    """The explicit finding: how many independent parties back this claim.

    Recomputed from the evidence by `Warrant`; carried explicitly so it appears
    in the report and can be audited rather than inferred. The oracle
    additionally validates the declared sources against the corpus provenance
    graph -- a resolver's self-report is checked, not trusted.
    """

    sources: frozenset[SourceSystem]
    rationale: str

    @property
    def independent_parties(self) -> frozenset[str]:
        return parties(self.sources)

    @property
    def independent_count(self) -> int:
        return len(self.independent_parties)

    @property
    def is_corroborated(self) -> bool:
        return self.independent_count >= 2


class ContradictionKind(enum.Enum):
    #: The attestation names rows that do not close to the bank amount.
    ATTESTED_COMPOSITION_DOES_NOT_CLOSE = "attested_composition_does_not_close"
    #: The rows chosen collectively declare a settlement reference the bank
    #: line does not carry.
    REFERENCE_MISMATCH = "reference_mismatch"
    #: The PSP claims a settlement the bank never posted.
    CLAIMED_CREDIT_NOT_ON_STATEMENT = "claimed_credit_not_on_statement"
    #: The bank posted a credit the PSP does not claim.
    UNCLAIMED_CREDIT_ON_STATEMENT = "unclaimed_credit_on_statement"
    #: A row is claimed by two bank lines.
    DOUBLE_ASSIGNMENT = "double_assignment"
    #: A credit was later reversed by a bank debit.
    CREDIT_REVERSED = "credit_reversed"
    #: A row's timestamp makes its membership impossible.
    TEMPORAL_IMPOSSIBILITY = "temporal_impossibility"
    #: ERP or GST says something incompatible with the ledger.
    THIRD_PARTY_DISAGREES = "third_party_disagrees"


@dataclass(frozen=True, slots=True)
class Contradiction:
    kind: ContradictionKind
    detail: str
    #: The sources that disagree. A contradiction between two sources of the
    #: same PARTY is a bug in that party's records; between two independent
    #: parties it is a finding.
    between: frozenset[SourceSystem]
    row_ids: tuple[str, ...] = ()

    @property
    def is_cross_party(self) -> bool:
        return len(parties(self.between)) >= 2


@dataclass(frozen=True, slots=True)
class Warrant:
    """What supports an assignment. No assignment may exist without one.

    The independence determination is RECOMPUTED from the evidence at
    construction. A resolver cannot assert independence it does not have.
    """

    evidence: tuple[Evidence, ...]
    independence: IndependenceDetermination
    contradictions: tuple[Contradiction, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ContractViolation("a warrant with no evidence is not a warrant")
        actual = frozenset().union(*(e.derived_from for e in self.evidence))
        if self.independence.sources != actual:
            raise ContractViolation(
                "independence determination disagrees with the evidence: "
                f"declared {sorted(s.value for s in self.independence.sources)}, "
                f"evidence gives {sorted(s.value for s in actual)}")

    @property
    def kinds(self) -> frozenset[EvidenceKind]:
        return frozenset(e.kind for e in self.evidence)

    def attesting(self, what: Attests) -> tuple[Evidence, ...]:
        return tuple(e for e in self.evidence if e.attests_to is what)

    @property
    def has_independent_corroboration(self) -> bool:
        return self.independence.is_corroborated

    @staticmethod
    def over(evidence: Sequence[Evidence], *, rationale: str,
             contradictions: Sequence[Contradiction] = ()) -> "Warrant":
        sources = (frozenset().union(*(e.derived_from for e in evidence))
                   if evidence else frozenset())
        return Warrant(evidence=tuple(evidence),
                       independence=IndependenceDetermination(
                           sources=sources, rationale=rationale),
                       contradictions=tuple(contradictions))


# --------------------------------------------------------------------------
# Compositions and candidate sets
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Composition:
    """One explanation of a bank credit: which rows made it up.

    Sorted tuples so equality, hashing and report output are order-independent.
    Money is integer paise, as everywhere in this repo.
    """

    credit_ids: tuple[str, ...]
    debit_ids: tuple[str, ...]
    credit_total: int
    debit_total: int

    def __post_init__(self) -> None:
        if (list(self.credit_ids) != sorted(self.credit_ids)
                or list(self.debit_ids) != sorted(self.debit_ids)):
            raise ContractViolation("composition ids must be sorted")
        overlap = set(self.credit_ids) & set(self.debit_ids)
        if overlap:
            raise ContractViolation(
                f"row on both sides of a composition: {sorted(overlap)}")

    @property
    def net(self) -> int:
        return self.credit_total - self.debit_total

    @property
    def row_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.credit_ids + self.debit_ids))


@dataclass(frozen=True, slots=True)
class RankingAnnotation:
    """An objective applied to an ALREADY-COMPLETE candidate set.

    Contract sec 2: no objective may filter candidates before uniqueness is
    tested. An objective may only RANK, and where it appears it must be
    labelled a modelling assumption. `applied_after_enumeration` is not a
    courtesy flag -- a resolver that sets it False is declaring a contract
    violation about itself, and the oracle reads it.
    """

    objective: str
    applied_after_enumeration: bool
    modelling_assumption: str

    def __post_init__(self) -> None:
        if not self.modelling_assumption.strip():
            raise ContractViolation(
                f"objective {self.objective!r} must state its modelling "
                "assumption; an unlabelled objective is a hidden premise")


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """The complete enumeration of closing subsets, or an explicit sample.

    `complete=False` means enumeration stopped early. The set is then a SAMPLE
    and the line is MORE ambiguous than its length suggests, never less. It is
    still reported in full, because the oracle checks whether the truth was in
    what the resolver actually constructed -- a resolver that discards a
    truncated set has thrown away the evidence of its own miss.

    When `ranked` is set, `candidates` is in the resolver's preference order
    and `candidates[0]` is its rank-1 pick. That pick is the input to the
    premise-sharing statistic (contract sec 6.2) and it is NOT an assignment.
    """

    candidates: tuple[Composition, ...]
    complete: bool
    enumeration_cap: int
    ranking: tuple[RankingAnnotation, ...] = ()
    ranked: bool = False

    def __post_init__(self) -> None:
        for annotation in self.ranking:
            if not annotation.applied_after_enumeration:
                raise ContractViolation(
                    f"objective {annotation.objective!r} filtered the candidate "
                    "set before uniqueness was tested (contract sec 2)")
        if self.ranking and not self.ranked:
            raise ContractViolation(
                "a ranking annotation without `ranked` set: the contract needs "
                "the rank order to measure premise sharing (sec 6.2)")

    @property
    def size(self) -> int:
        return len(self.candidates)

    @property
    def rank_one(self) -> Composition | None:
        """The resolver's preferred candidate, or None if it did not rank.

        Reading this is NOT reading an answer. It is how the oracle measures
        whether the resolver's objective agrees with the generator's rule more
        often than chance -- which is the only falsifiable form of the
        premise-sharing test.
        """
        return self.candidates[0] if (self.ranked and self.candidates) else None


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------


class UnmatchedReason(enum.Enum):
    """Why a row correctly has no bank credit. Each must be DERIVED, not
    assumed -- the oracle scores the reason, not merely the classification."""

    NETTED_OUT = "netted_out"                    # full refund pre-eligibility
    ROLLED_FORWARD = "rolled_forward"            # eligible, not selected
    NOT_YET_ELIGIBLE = "not_yet_eligible"        # T+2 not reached at horizon
    DISPUTE_HELD = "dispute_held"                # locked funds
    DEBIT_DEFERRED = "debit_deferred"            # non-negative payout rule
    FAILED_AT_GATEWAY = "failed_at_gateway"      # never captured


class UnresolvedReason(enum.Enum):
    """Why the resolver said nothing. An ENUM, not free text, because the
    oracle reports `Unresolved` split by reason per axis cell -- and
    `ENUMERATION_TRUNCATED` is the reason that would otherwise let the hardest
    cells of the corpus produce the cleanest-looking numbers."""

    NO_SUBSET_CLOSES = "no_subset_closes"
    ENUMERATION_TRUNCATED = "enumeration_truncated"
    TIME_BUDGET_EXCEEDED = "time_budget_exceeded"
    POOL_EMPTY = "pool_empty"
    NOT_OUR_CREDIT = "not_our_credit"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Verified:
    """A composition was CLAIMED by one party and a falsifiable CONSEQUENCE of
    that claim was confirmed by an INDEPENDENT party.

    Read the claim exactly: it is not "the composition is proven". No party
    outside the PSP ever witnesses which rows formed a batch. What `Verified`
    asserts is that the composition claim made a checkable prediction about an
    independent party's records, and the prediction held -- and, crucially,
    that it COULD have failed, which is what `AttestationDiscrepancy` records
    when it does.

    `rival_closure_count` is how strong that is. A consequence confirmed when
    400 rival compositions predict the same consequence is weak corroboration
    of THIS composition, and the report must be able to say so rather than
    presenting every `Verified` as equally solid.

    The only outcome that may consume pool rows, and the only outcome whose
    wrongness is a build failure rather than a measurement.
    """

    bank_index: int
    composition: Composition
    warrant: Warrant
    #: Closing subsets of the pool at this line under NO objective filter,
    #: including the one claimed. 1 means the consequence was decisive. None
    #: is NOT permitted -- an unmeasured strength is an unstated weakness.
    rival_closure_count: int
    #: True when `rival_closure_count` is a floor because enumeration stopped.
    rival_count_is_lower_bound: bool = False

    def __post_init__(self) -> None:
        if not self.warrant.attesting(Attests.COMPOSITION):
            raise ContractViolation(
                "Verified needs a source that NAMES a composition; a bank "
                "reference attests to a credit's existence, never to which "
                "rows composed it (contract sec 3.2)")
        if not self.warrant.attesting(Attests.CONSEQUENCE):
            raise ContractViolation(
                "Verified needs a confirmed falsifiable consequence of the "
                "composition claim; without one nothing was corroborated")
        if not self.warrant.has_independent_corroboration:
            raise ContractViolation(
                "Verified requires two independent parties; warrant names "
                f"{sorted(self.warrant.independence.independent_parties)}")
        if self.warrant.contradictions:
            raise ContractViolation(
                "Verified cannot carry a contradiction -- that is an "
                "AttestationDiscrepancy: "
                f"{[c.kind.value for c in self.warrant.contradictions]}")
        if self.rival_closure_count < 1:
            raise ContractViolation(
                "rival_closure_count must include the claimed composition, so "
                "it is at least 1; 0 means it was never measured")

    @property
    def corroboration_is_decisive(self) -> bool:
        """The consequence check could only have been passed by this
        composition. Reported per-cell; NOT required, because demanding it
        would make `Verified` unreachable on exactly the large pools the
        corpus exists to explore."""
        return self.rival_closure_count == 1 and not self.rival_count_is_lower_bound

    @property
    def assigned_rows(self) -> tuple[str, ...]:
        return self.composition.row_ids


@dataclass(frozen=True, slots=True)
class AttestationDiscrepancy:
    """The sources disagree. The highest-value output this contract defines.

    The old engine had no way to express this. With one effective source there
    was nothing to disagree with, and its only vocabulary for "something is
    off" was `Unresolved`, which says "I could not explain this" rather than
    "the record is wrong". Carries NO composition -- a discrepancy is a finding
    about the record, not a claim about which rows settled.
    """

    bank_index: int
    contradiction: Contradiction
    warrant: Warrant
    attested_row_ids: tuple[str, ...] = ()
    attested_net: int | None = None
    bank_amount: int | None = None

    def __post_init__(self) -> None:
        if not self.warrant.contradictions:
            raise ContractViolation(
                "AttestationDiscrepancy requires the contradiction on its warrant")

    @property
    def assigned_rows(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Reconstructed:
    """Unattested, unique closure under NO objective filter, AND exclusive
    across the window.

    STRICTLY WEAKER than `Verified`, and named so the two cannot be confused
    at a call site or in a report.

    The cross-line requirement is not decoration. At all three bank lines that
    produced the 50 wrong rows in `investigation/DEFECT_REPORT.md` sec 1, the
    pool admitted EXACTLY ONE closing subset -- `OPTIMAL`, untruncated. Per-
    credit uniqueness held perfectly and the answer was still wrong, because
    those rows were the true composition of a LATER credit. Uniqueness is a
    per-credit predicate answering a cross-credit question, so this outcome
    demands the cross-credit evidence explicitly.
    """

    bank_index: int
    composition: Composition
    warrant: Warrant

    def __post_init__(self) -> None:
        if EvidenceKind.UNIQUE_CLOSURE_UNFILTERED not in self.warrant.kinds:
            raise ContractViolation(
                "Reconstructed requires UNIQUE_CLOSURE_UNFILTERED: uniqueness "
                "established with no objective filtering the candidate set "
                "(contract sec 2)")
        if EvidenceKind.CROSS_LINE_EXCLUSIVITY not in self.warrant.kinds:
            raise ContractViolation(
                "Reconstructed requires CROSS_LINE_EXCLUSIVITY: unique closure "
                "held at all three lines that produced the 50 wrong rows. "
                "Uniqueness alone is not the missing property (contract sec 4.3)")
        if self.warrant.has_independent_corroboration:
            raise ContractViolation(
                "two independent parties agree -- this is Verified, and "
                "reporting it as Reconstructed understates the claim")

    @property
    def assigned_rows(self) -> tuple[str, ...]:
        return self.composition.row_ids


@dataclass(frozen=True, slots=True)
class Ambiguous:
    """Two or more compositions explain this credit. There is no answer here.

    Deliberately exposes NO single assignment, and `decomposition` is not a
    missing feature -- reading it raises `UnrepresentableClaim` so the error
    names the intent. `common_rows` is an ambiguity PROPERTY and is NEVER an
    assignment; that is defect D3 of the previous engine, which assigned rows
    from exactly this set with no corroboration at all.
    """

    bank_index: int
    candidate_set: CandidateSet
    warrant: Warrant

    def __post_init__(self) -> None:
        if self.candidate_set.size < 2:
            raise ContractViolation("Ambiguous requires at least two candidates")

    def __getattr__(self, name: str):
        if name in {"decomposition", "composition", "best", "chosen", "answer"}:
            raise UnrepresentableClaim(
                f"Ambiguous has no {name!r} and never will. Two or more "
                "compositions explain this credit; naming one would assert "
                "something no evidence supports. Read `candidate_set`, or "
                "`candidate_set.rank_one` if you want the resolver's "
                "preference -- which is a preference, not an assignment.")
        raise AttributeError(name)

    @property
    def candidate_count(self) -> int:
        return self.candidate_set.size

    @property
    def common_rows(self) -> tuple[str, ...]:
        """Rows present in EVERY candidate.

        A PROPERTY OF THE AMBIGUITY, reported for the human reading the
        exception queue. It is NOT an assignment and must never be consumed:
        "in every candidate" is not evidence a row settled here, only that
        every explanation the resolver CONSTRUCTED contains it. Empty when the
        set is incomplete, because an unseen candidate can drop any of them.
        """
        if not self.candidate_set.complete:
            return ()
        common = set(self.candidate_set.candidates[0].row_ids)
        for candidate in self.candidate_set.candidates[1:]:
            common &= set(candidate.row_ids)
        return tuple(sorted(common))

    @property
    def contested_rows(self) -> tuple[str, ...]:
        union: set[str] = set()
        for candidate in self.candidate_set.candidates:
            union |= set(candidate.row_ids)
        return tuple(sorted(union - set(self.common_rows)))

    @property
    def assigned_rows(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Unresolved:
    """Not enough evidence to say anything. An honest empty answer -- and a
    DEFECT on the determined subpopulation (contract sec 6.1).

    `partial_candidates` is not optional bookkeeping. When enumeration
    truncated, the oracle must still be able to ask whether the truth was in
    what the resolver built; a resolver that discards the set has destroyed the
    evidence of its own miss.
    """

    bank_index: int
    reason: UnresolvedReason
    pool_size: int
    warrant: Warrant
    detail: str = ""
    nearest_residual: int | None = None
    partial_candidates: CandidateSet | None = None

    @property
    def assigned_rows(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class CorrectlyUnmatched:
    """These rows correctly have no bank credit, for a DERIVED reason.

    The reason is scored by the oracle. "Unmatched, and I have a label for it"
    is not the claim; "unmatched BECAUSE of this, and here is what says so" is.
    """

    row_ids: tuple[str, ...]
    reason: UnmatchedReason
    warrant: Warrant

    @property
    def assigned_rows(self) -> tuple[str, ...]:
        return ()


LineOutcome = (Verified | AttestationDiscrepancy | Reconstructed
               | Ambiguous | Unresolved)
Outcome = LineOutcome | CorrectlyUnmatched


def may_consume(outcome: Outcome) -> bool:
    """The single consumption predicate. Contract sec 2.4.

    Only `Verified` removes rows from later pools. Contested rows stay in the
    pool -- an ambiguity is not a reason to believe the rows are spent, and
    treating it as one is how one damaged bank line damages the next (defect
    D2: one reversal, two ruined lines, 50 rows).
    """
    return isinstance(outcome, Verified)


# --------------------------------------------------------------------------
# The determined subpopulation -- why abstention is not free
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeterminedInstance:
    """A bank line the CORPUS knows is determined, declared by ground truth.

    Contract sec 6.1. Without this, every hard guarantee in this contract is
    satisfied by a resolver that returns `Unresolved` to everything: no wrong
    `Verified`, no uncorroborated warrant, no ambiguity missing its truth, no
    unwarranted assignment -- all zero, all vacuous. And the largest pools, the
    most adversarial cells, would produce the cleanest numbers in the report
    because enumeration truncates there first.

    An instance is determined when, under an enumerator INDEPENDENT of any
    resolver and with no objective:

      * exactly one subset of the pool closes to the credit, AND
      * that subset does not close any other unexplained credit in the window,
        AND
      * the attestation is present and agrees with it.

    On these, and only these, `Unresolved` and `Ambiguous` are FAILURES.
    """

    bank_index: int
    true_composition_row_ids: tuple[str, ...]
    closure_count: int
    closure_complete: bool

    def __post_init__(self) -> None:
        if self.closure_count != 1 or not self.closure_complete:
            raise ContractViolation(
                "a DeterminedInstance has exactly one closing subset, proven "
                "by a COMPLETE enumeration; anything else is not determined "
                f"(count={self.closure_count}, complete={self.closure_complete})")


@dataclass(frozen=True, slots=True)
class ReconstructibleInstance:
    """A bank line that is UNATTESTED and still has exactly one explanation.

    Contract sec 6.4. **Amendment, adopted 2026-08-24, after corpus generation
    had begun.** It is dated and justified here rather than folded in silently,
    because the contract's whole claim on being trustworthy is that it was
    written before the data.

    ## Why it had to be added

    Measured on the generated corpus:

        axis point     determined   lines with unique complete closure
        A20_B100_Cmax      10            11  (all attested)
        A20_B75_Cmax        8            12  (3 unattested)
        A20_B50_Cmax        5            11  (5 unattested)
        A20_B0_Cmax         0            11  (11 unattested)

    At 0% coverage **every gate was vacuous**. Section 6.3's theorem forces
    `|Verified| = 0`, so the wrong-Verified and independence gates have nothing
    to check; and `DeterminedInstance` requires the attestation, so the
    abstention gate had an EMPTY subpopulation. A resolver returning
    `Unresolved` to everything scored perfectly on the one cell that is purely
    about reconstruction -- and it is the cell where the branch that produced
    all 50 wrong answers actually lives.

    That is the same hole sec 6.1 exists to close, reopened one axis over.

    ## What it does NOT change

    No outcome semantics, no existing gate, no generated dataset. It is derived
    from closure registers already present in every ground-truth key, so
    nothing was regenerated to make it true -- which is what keeps this an
    addition rather than a re-cut of the benchmark after seeing results.

    On these lines `Reconstructed` is achievable, so `Unresolved` and
    `Ambiguous` are failures. `Verified` is NOT expected -- there is no
    attestation to corroborate.
    """

    bank_index: int
    true_composition_row_ids: tuple[str, ...]
    closure_count: int
    closure_complete: bool
    #: The subset closes no OTHER unexplained credit in the window. Without
    #: this the line is not reconstructible -- it is the 50-row failure
    #: (sec 4.3), where per-credit closure was unique and the answer was wrong.
    cross_line_exclusive: bool

    def __post_init__(self) -> None:
        if self.closure_count != 1 or not self.closure_complete:
            raise ContractViolation(
                "a ReconstructibleInstance has exactly one closing subset, "
                "proven by a COMPLETE enumeration "
                f"(count={self.closure_count}, complete={self.closure_complete})")
        if not self.cross_line_exclusive:
            raise ContractViolation(
                "a subset that also closes another unexplained credit is not "
                "reconstructible; uniqueness held at all three lines that "
                "produced the 50 wrong rows (sec 4.3)")


# --------------------------------------------------------------------------
# Reported output shape -- an accounting, not a rate
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutcomeAccounting:
    """The six-way accounting the contract requires instead of a match rate.

    `mean_candidate_set_size` is reported ALWAYS and unprompted. Without it,
    "declined fewer lines" and "enumerated more candidates until the truth was
    somewhere in the set" are indistinguishable, and the second is not skill.

    `unresolved_by_reason` is reported for the same reason one axis up:
    without it, "declined honestly" and "the enumerator gave up" are
    indistinguishable, and only the first is a decision.
    """

    verified: int
    attestation_discrepancy: int
    reconstructed: int
    ambiguous: int
    unresolved: int
    correctly_unmatched: int
    reasons: dict[str, dict[str, int]] = field(default_factory=dict)
    mean_candidate_set_size: float = 0.0
    max_candidate_set_size: int = 0
    incomplete_enumerations: int = 0
    #: Verified where the consequence check could have been passed by a rival
    #: composition. Measured, never gated -- it is a strength report, not a
    #: defect, but an unreported strength distribution is a hidden weakness.
    verified_non_decisive: int = 0

    @property
    def total_lines(self) -> int:
        return (self.verified + self.attestation_discrepancy + self.reconstructed
                + self.ambiguous + self.unresolved)


@dataclass(frozen=True, slots=True)
class ResolverOutput:
    """What a resolver returns. The oracle consumes exactly this.

    `row_assignments` is DERIVED from the outcomes rather than reported
    alongside them, so a row cannot be assigned by a path that produced no
    outcome. That is not a convenience -- it is the structural form of the
    oracle's fourth must-be-zero check.
    """

    resolver: str
    dataset: str
    line_outcomes: tuple[LineOutcome, ...]
    unmatched: tuple[CorrectlyUnmatched, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[str, int] = {}
        for outcome in self.line_outcomes:
            for row_id in outcome.assigned_rows:
                if row_id in seen:
                    raise ContractViolation(
                        f"row {row_id} assigned to bank[{seen[row_id]}] and "
                        f"bank[{outcome.bank_index}]; a row settles once")
                seen[row_id] = outcome.bank_index

    @property
    def row_assignments(self) -> dict[str, int]:
        return {row_id: outcome.bank_index
                for outcome in self.line_outcomes
                for row_id in outcome.assigned_rows}

    def by_line(self) -> dict[int, LineOutcome]:
        return {outcome.bank_index: outcome for outcome in self.line_outcomes}

    def warrant_for_row(self, row_id: str) -> Warrant | None:
        for outcome in self.line_outcomes:
            if row_id in outcome.assigned_rows:
                return outcome.warrant
        return None

    def abstention_failures(
        self,
        determined: Sequence[DeterminedInstance | ReconstructibleInstance],
    ) -> list[tuple[int, str]]:
        """Instances the resolver failed to resolve. GATED AT ZERO.

        The counterweight to the soundness gates: it cannot be passed by
        silence, because silence is exactly what it measures. Accepts both
        subpopulations -- `DeterminedInstance` (attested, sec 6.1) and
        `ReconstructibleInstance` (unattested, sec 6.4) -- because the hole is
        the same one and abstaining is a defect on either.
        """
        outcomes = self.by_line()
        failures: list[tuple[int, str]] = []
        for instance in determined:
            outcome = outcomes.get(instance.bank_index)
            if outcome is None:
                failures.append((instance.bank_index, "no outcome emitted"))
            elif isinstance(outcome, Unresolved):
                failures.append((instance.bank_index,
                                 f"Unresolved({outcome.reason.value}) on a "
                                 "determined instance"))
            elif isinstance(outcome, Ambiguous):
                failures.append((instance.bank_index,
                                 f"Ambiguous({outcome.candidate_count}) on an "
                                 "instance with exactly one closing subset"))
        return failures

    def accounting(self) -> OutcomeAccounting:
        counts = dict.fromkeys(
            ("verified", "attestation_discrepancy", "reconstructed",
             "ambiguous", "unresolved"), 0)
        sizes: list[int] = []
        incomplete = 0
        non_decisive = 0
        reasons: dict[str, dict[str, int]] = {
            "unresolved": {}, "attestation_discrepancy": {},
            "correctly_unmatched": {}}

        def bump(bucket: str, key: str) -> None:
            reasons[bucket][key] = reasons[bucket].get(key, 0) + 1

        for outcome in self.line_outcomes:
            if isinstance(outcome, Verified):
                counts["verified"] += 1
                sizes.append(1)
                non_decisive += not outcome.corroboration_is_decisive
            elif isinstance(outcome, AttestationDiscrepancy):
                counts["attestation_discrepancy"] += 1
                bump("attestation_discrepancy", outcome.contradiction.kind.value)
            elif isinstance(outcome, Reconstructed):
                counts["reconstructed"] += 1
                sizes.append(1)
            elif isinstance(outcome, Ambiguous):
                counts["ambiguous"] += 1
                sizes.append(outcome.candidate_count)
                incomplete += not outcome.candidate_set.complete
            elif isinstance(outcome, Unresolved):
                counts["unresolved"] += 1
                bump("unresolved", outcome.reason.value)
        for item in self.unmatched:
            reasons["correctly_unmatched"][item.reason.value] = (
                reasons["correctly_unmatched"].get(item.reason.value, 0)
                + len(item.row_ids))
        return OutcomeAccounting(
            verified=counts["verified"],
            attestation_discrepancy=counts["attestation_discrepancy"],
            reconstructed=counts["reconstructed"],
            ambiguous=counts["ambiguous"],
            unresolved=counts["unresolved"],
            correctly_unmatched=sum(len(i.row_ids) for i in self.unmatched),
            reasons=reasons,
            mean_candidate_set_size=(sum(sizes) / len(sizes)) if sizes else 0.0,
            max_candidate_set_size=max(sizes) if sizes else 0,
            incomplete_enumerations=incomplete,
            verified_non_decisive=non_decisive)
