"""The four-stage cascade.

    Stage 1  exact join          settlement_id, order_id
    Stage 2  fuzzy blocking      (amount, date) fallback; gated ERP candidates
    Stage 3  constrained solver   CP-SAT enumeration + Hungarian residual
    Stage 4  exception routing    deterministic classification, LLM narration

Each stage sees only what earlier stages could not resolve, so a stage's
contribution is measurable on its own. `stage_contributions()` is what the eval
report uses to show that later stages do real work rather than restating Stage 1.

Nothing in this package reads the isolated answer key. The cascade is
judgeable without it, which is the point: if the solver needed the answers to
run, it would not be a solver.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .loaders import Dataset, load
from .llm import Explainer, get_explainer
from .model import Ambiguous, Determinate, Unresolved
from . import stage1_exact, stage2_fuzzy, stage3_solver, stage4_exceptions


@dataclass
class CascadeResult:
    dataset: Dataset
    stage1: stage1_exact.Stage1Result
    stage2: stage2_fuzzy.Stage2Result
    stage3: stage3_solver.Stage3Result
    stage4: stage4_exceptions.Stage4Result
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def bank_to_batch(self) -> dict[int, str]:
        merged = dict(self.stage1.bank_to_batch)
        merged.update(self.stage2.bank_to_batch)
        return merged

    @property
    def matched_row_ids(self) -> set[str]:
        """Rows placed in a specific bank credit, with a closing proof."""
        return set(self.stage3.assigned)

    @property
    def contested_row_ids(self) -> set[str]:
        """Rows known to be in a batch, but not known WHICH decomposition."""
        return set(self.stage3.contested)

    @property
    def accounted_row_ids(self) -> set[str]:
        """Rows correctly and explainably NOT matched."""
        return {item.entity_id for item in self.stage4.exceptions
                if item.type in stage4_exceptions.NOT_A_PROBLEM}

    def stage_contributions(self) -> dict[str, int]:
        """Bank lines resolved by each stage, cumulatively."""
        stage1_lines = len(self.stage1.bank_to_batch)
        stage2_lines = stage1_lines + len(self.stage2.bank_to_batch)
        stage3_determinate = sum(
            1 for item in self.stage3.reconstructions
            if isinstance(item.resolution, Determinate))
        return {
            "stage1_bank_lines": stage1_lines,
            "stage1_plus_stage2_bank_lines": stage2_lines,
            "stage3_determinate_reconstructions": stage3_determinate,
            "stage3_ambiguous_reconstructions": len(self.stage3.ambiguous_indexes),
            "stage3_unresolved_reconstructions": sum(
                1 for item in self.stage3.reconstructions
                if isinstance(item.resolution, Unresolved)),
            "total_bank_lines": len(self.dataset.bank),
        }

    def balance_violations(self) -> list[str]:
        """Determinate resolutions whose arithmetic does not close.

        Should always be empty: `Determinate.__post_init__` raises on
        construction. Re-checked here so the postcondition is asserted at the
        boundary as well as at the constructor -- a bug to surface loudly, not
        an exception to route away.
        """
        broken = []
        for item in self.stage3.reconstructions:
            resolution = item.resolution
            if isinstance(resolution, Determinate) and not resolution.proof.holds:
                broken.append(f"bank[{item.bank_index}]: {resolution.proof.describe()}")
        return broken


def run(dataset: Dataset | None = None, explainer: Explainer | None = None,
        llm: str = "deterministic") -> CascadeResult:
    dataset = dataset or load()
    explainer = explainer or get_explainer(llm)
    timings: dict[str, float] = {}

    began = time.perf_counter()
    one = stage1_exact.run(dataset)
    timings["stage1"] = time.perf_counter() - began

    began = time.perf_counter()
    two = stage2_fuzzy.run(dataset, one)
    timings["stage2"] = time.perf_counter() - began

    merged = dict(one.bank_to_batch)
    merged.update(two.bank_to_batch)

    began = time.perf_counter()
    three = stage3_solver.run(dataset, merged)
    timings["stage3"] = time.perf_counter() - began

    began = time.perf_counter()
    four = stage4_exceptions.run(dataset, one, three, explainer)
    timings["stage4"] = time.perf_counter() - began
    timings["total"] = sum(timings.values())

    return CascadeResult(dataset=dataset, stage1=one, stage2=two, stage3=three,
                         stage4=four, timings=timings)
