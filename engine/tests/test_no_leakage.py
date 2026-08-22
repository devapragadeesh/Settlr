"""The frozen dataset must not tell the solver the answers.

Ground truth lives in engine/ground_truth/. Nothing under engine/data/ may
carry a class label, a scenario name, a batch decomposition, or any other
token that would let a solver shortcut the work.
"""

import json
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent
DATA = ENGINE / "data"
TRUTH = ENGINE / "ground_truth"

#: tokens that would give the game away if they appeared in shipped data
FORBIDDEN = [
    "ambiguous", "tying", "decomposition", "rolled_forward", "roll_forward",
    "subset_sum", "subset-sum", "ground_truth", "netted_out", "scenario",
    "planted", "c01_", "c02_", "c03_", "c04_", "c05_", "c06_", "c07_",
    "c08_", "c09_", "c10_", "c11_", "c12_", "c13_", "c14_", "c15_",
    "clean_1to1", "cross_month", "schema_variance", "itc_at_risk",
    "on_hold_dispute", "corrupt", "unsettled_reason", "hard_case",
]

#: the spike's own scenario labels, which live in the captured notes
SPIKE_LABELS = ["a_simple", "b_fullrefund", "c_subset", "d_partialrefund",
                "f_nb_", "f_wallet_", "h_failed"]


def data_files():
    return sorted(p for p in DATA.iterdir() if p.is_file())


@pytest.mark.parametrize("path", data_files(), ids=lambda p: p.name)
def test_no_ground_truth_token_appears_in_shipped_data(path):
    text = path.read_text().lower()
    hits = [token for token in FORBIDDEN if token in text]
    assert not hits, f"{path.name} leaks: {hits}"


@pytest.mark.parametrize("path", data_files(), ids=lambda p: p.name)
def test_no_spike_scenario_label_survived_into_shipped_data(path):
    text = path.read_text()
    hits = [label for label in SPIKE_LABELS if label in text]
    assert not hits, f"{path.name} leaks captured spike scenario labels: {hits}"


def test_ground_truth_is_not_referenced_by_any_shipped_data_file():
    for path in data_files():
        assert "ground_truth" not in path.read_text()


def test_ground_truth_lives_outside_the_data_directory():
    assert TRUTH.resolve() != DATA.resolve()
    assert not (DATA / "ground_truth.json").exists()
    assert (TRUTH / "ground_truth.json").exists()


#: the ONLY modules allowed to touch the ground-truth key, as REPO-RELATIVE
#: paths. Basenames were used until Phase 4 and were too weak: `report.py`
#: exists under both `engine/` and `eval/`, so an allowlist keyed on the name
#: alone would have admitted any future file that happened to be called that.
#:
#: Two data-side modules that run before any solver exists -- the generator
#: writes the key, the reporter reads it to describe the dataset -- and the
#: two `eval/` modules, which score AGAINST the key by design and are the one
#: package permitted to. Any `matching/` module appearing here is a freeze
#: violation.
GROUND_TRUTH_ALLOWLIST = {
    "engine/generator.py",
    "engine/report.py",
    "eval/metrics.py",
    "eval/report.py",
    "eval/holdout_report.py",
    "eval/scale_report.py",
}

#: scanned repo-wide, not just under `engine/`. The original version of this
#: test globbed `engine/` only, because it was written in Phase 1 when nothing
#: else existed; it would NOT have caught a violation in `matching/`.
#: `tests/test_isolation.py` independently enforces the same property over
#: `matching/` by AST, and both are kept: one proves no solver module names
#: the key, the other proves nothing ANYWHERE outside the allowlist does.
SCANNED_PACKAGES = ("engine", "matching", "eval")


def _scanned_modules():
    for package in SCANNED_PACKAGES:
        for path in sorted((REPO / package).rglob("*.py")):
            if "tests" in path.relative_to(REPO).parts:
                continue
            yield path


def test_no_module_outside_the_allowlist_reads_the_ground_truth_path():
    """The freeze is only meaningful if no solver can reach the key."""
    offenders = []
    for path in _scanned_modules():
        relative = path.relative_to(REPO).as_posix()
        if relative in GROUND_TRUTH_ALLOWLIST:
            continue
        if "ground_truth" in path.read_text():
            offenders.append(relative)
    assert not offenders, f"these modules reference the ground truth: {offenders}"


def test_the_scan_actually_reaches_the_solver_package():
    """Guards the bug this test itself had: a scan that silently covers
    nothing proves nothing. If `matching/` stops being scanned, fail here
    rather than passing vacuously."""
    scanned = {p.relative_to(REPO).as_posix() for p in _scanned_modules()}
    assert any(p.startswith("matching/") for p in scanned), scanned
    assert "matching/stage3_solver.py" in scanned


def test_no_matching_module_reads_the_ground_truth():
    """Stated directly, so the property does not depend on reading an
    allowlist correctly."""
    offenders = [p.relative_to(REPO).as_posix()
                 for p in sorted((REPO / "matching").rglob("*.py"))
                 if "ground_truth" in p.read_text()]
    assert not offenders, offenders


def test_the_allowlist_stays_small():
    assert GROUND_TRUTH_ALLOWLIST == {
        "engine/generator.py", "engine/report.py",
        "eval/metrics.py", "eval/report.py",
        "eval/holdout_report.py", "eval/scale_report.py",
    }, "someone widened the ground-truth allowlist"
    assert not any(p.startswith("matching/") for p in GROUND_TRUTH_ALLOWLIST), \
        "a solver module was added to the ground-truth allowlist"


def test_the_simulator_never_mentions_the_ground_truth():
    """The simulator produces the truth; it must not read it back."""
    assert "ground_truth" not in (ENGINE / "simulator.py").read_text()


def test_entity_ids_encode_nothing(rows):
    """Ids must be opaque -- no ordering, no class, no batch membership."""
    for row in rows:
        prefix, _, body = row["entity_id"].partition("_")
        assert prefix in {"pay", "rfnd", "adj"}
        assert len(body) == 14
        assert re.fullmatch(r"[0-9A-Za-z]{14}", body), row["entity_id"]


def test_settlement_ids_are_not_sequential(rows, truth):
    ids = [b["settlement_id"] for b in truth["batches"]]
    assert ids != sorted(ids), "settlement ids are in date order -- that leaks"
    for sid in ids:
        assert re.fullmatch(r"setl_[0-9A-Za-z]{14}", sid)


def test_notes_content_carries_no_class_information(rows, truth):
    """Notes must not correlate with class membership -- comparing KEYS AND
    VALUES. Comparing keys alone once let a distinctive `reason` value through.

    Compared WITHIN a row type: `notes.reason` exists only on refunds, but
    `type: "refund"` is already on the row, so that is redundancy, not leakage.
    Values occurring on a single row are also skipped -- a unique cart id
    carries no distributional signal.
    """
    from collections import Counter
    hard = {e for e, classes in truth["row_classes"].items()
            if set(classes) - {"c01_clean_1to1"}}
    frequency = Counter()
    for row in rows:
        if isinstance(row["notes"], dict):
            frequency.update((row["type"], *pair) for pair in row["notes"].items())

    for row_type in {r["type"] for r in rows}:
        hard_notes, clean_notes = set(), set()
        for row in rows:
            if row["type"] != row_type or not isinstance(row["notes"], dict):
                continue
            target = hard_notes if row["entity_id"] in hard else clean_notes
            target.update(pair for pair in row["notes"].items()
                          if frequency[(row_type, *pair)] > 1)
        only_hard = hard_notes - clean_notes
        if clean_notes:
            assert not only_hard, \
                f"{row_type}: these note pairs appear only on hard rows: {only_hard}"


def test_a_repeated_note_value_never_marks_a_single_class(rows, truth):
    """The specific failure mode: one `reason` string used by calibration
    refunds and by nothing else."""
    from collections import Counter
    classes_of = {e: set(c) for e, c in truth["row_classes"].items()}
    by_pair: dict[tuple, list] = {}
    for row in rows:
        if isinstance(row["notes"], dict):
            for pair in row["notes"].items():
                by_pair.setdefault(pair, []).append(row["entity_id"])
    for pair, entities in by_pair.items():
        if len(entities) < 3:
            continue
        label_sets = [classes_of.get(e, set()) for e in entities]
        shared = set.intersection(*label_sets) if label_sets else set()
        assert not shared - {"c13_schema_variance"}, \
            f"note {pair} implies class {shared}"


def test_row_order_does_not_group_by_class(rows, truth):
    """Rows are in created_at order; classes must be interleaved."""
    hard = {e for e, classes in truth["row_classes"].items()
            if "c05_subset_sum_rolled_forward" in classes
            or "c08_dispute_hold" in classes}
    positions = [i for i, r in enumerate(rows) if r["entity_id"] in hard]
    assert positions
    assert max(positions) - min(positions) > len(rows) // 2, \
        "hard rows are clustered in the file"


#: words that describe why the GENERATOR made a row, rather than a fact about
#: the row. A provenance field containing any of these is a stage direction.
STAGE_DIRECTIONS = ["calibration", "ambiguity", "pressure", "planted", "decoy",
                    "forced", "deliberate", "so that", "in order to"]


def test_source_ref_describes_provenance_never_the_generators_purpose(rows):
    for row in rows:
        lowered = row["source_ref"].lower()
        hits = [word for word in STAGE_DIRECTIONS if word in lowered]
        assert not hits, (row["entity_id"], row["source_ref"], hits)


def test_no_repeated_source_ref_is_confined_to_the_ambiguous_batches(rows, truth):
    """An earlier draft stamped calibration debits with a distinctive
    `source_ref`, so a two-token grep named both unresolvable batches."""
    from collections import Counter
    ambiguous = {b["settlement_id"] for b in truth["batches"] if b["ambiguous"]}
    tally = Counter(r["source_ref"] for r in rows)
    for ref, count in tally.items():
        if count < 2:
            continue          # a one-row ref carries no distributional signal
        sids = {r["settlement_id"] for r in rows if r["source_ref"] == ref}
        assert not (sids and sids <= ambiguous), ref


def test_no_notes_value_is_confined_to_the_ambiguous_batches(rows, truth):
    """The same leak in a different field: calibration refunds once used a
    `reason` value no organic refund used."""
    ambiguous = {b["settlement_id"] for b in truth["batches"] if b["ambiguous"]}
    values: dict[tuple, set] = {}
    for row in rows:
        if not isinstance(row["notes"], dict):
            continue
        for pair in row["notes"].items():
            values.setdefault(pair, set()).add(row["settlement_id"])
    for pair, sids in values.items():
        if len(sids) < 2:
            continue
        assert not sids <= ambiguous, pair


def test_no_description_text_marks_a_planted_batch(rows, truth):
    ambiguous = {b["settlement_id"] for b in truth["batches"] if b["ambiguous"]}
    texts: dict[str, set] = {}
    for row in rows:
        if row["description"]:
            texts.setdefault(row["description"], set()).add(row["settlement_id"])
    for text, sids in texts.items():
        if len(sids) < 2:
            continue
        assert not sids <= ambiguous, text


def test_the_ground_truth_key_actually_contains_the_answers():
    """The converse check: the key must be worth isolating."""
    truth = json.loads((TRUTH / "ground_truth.json").read_text())
    for key in ("settled_in", "unsettled_reason", "batches", "row_classes",
                "netted_out", "itc_at_risk", "payments_missing_from_erp"):
        assert truth[key], key
    assert all("credit_ids" in b and "tying_decompositions" in b
               for b in truth["batches"])
