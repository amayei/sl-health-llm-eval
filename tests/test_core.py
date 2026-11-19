import json
import shutil
from pathlib import Path

import pytest

from slheval.__main__ import main
from slheval.analyse import MIN_KRIO_ITEMS, summarise
from slheval.data import krio_as_items, read_jsonl, validate_items, validate_krio
from slheval.prompts import build_prompt, content_index, correct_letter, parse_letter, permutation
from slheval.stats import bootstrap_ci, wilson_ci

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.jsonl"
CONFIG = ROOT / "config" / "models.json"


# ---------- parsing ----------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("A", "A"),
        ("(B)", "B"),
        ("**C**", "C"),
        ("D.", "D"),
        ("B) Rapid intravenous fluids", "B"),
        ("The answer is B.", "B"),
        ("Answer: C", "C"),
        ("I think A at first, but the best answer is **D**", "D"),
        ("Option B", "B"),
        ("A patient with fever should be isolated.", None),
        ("None of the above", None),
        ("The best choice is a", None),
        ("The answer is Dehydration", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_letter(text, expected):
    assert parse_letter(text) == expected


# ---------- prompts ----------
def test_permutation_is_valid_and_deterministic():
    for rep in range(3):
        perm = permutation("SURV-01", rep, 1)
        assert sorted(perm) == [0, 1, 2, 3]
        assert perm == permutation("SURV-01", rep, 1)
    perms = {tuple(permutation(f"X-{i}", 0, 1)) for i in range(40)}
    assert len(perms) > 5


def test_letter_mapping_round_trip():
    for item in read_jsonl(ITEMS):
        for rep in range(3):
            perm = permutation(item["id"], rep, 7)
            letter = correct_letter(item["answer"], perm)
            assert content_index(letter, perm) == item["answer"]
            prompt = build_prompt(item["question"], item["options"], perm)
            shown = [line for line in prompt.splitlines() if line[:2] in ("A.", "B.", "C.", "D.")]
            assert shown["ABCD".index(letter)][3:] == item["options"][item["answer"]]


# ---------- statistics ----------
def test_wilson_known_value():
    lo, hi = wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)


def test_bootstrap_deterministic_and_sensible():
    values = [0, 1] * 20
    a = bootstrap_ci(values, n_boot=2000, seed=5)
    assert a == bootstrap_ci(values, n_boot=2000, seed=5)
    assert a[0] < 0.5 < a[1]
    assert bootstrap_ci([1.0] * 10, n_boot=500) == (1.0, 1.0)


# ---------- dataset ----------
def test_real_dataset_is_valid():
    items = read_jsonl(ITEMS)
    problems, warnings = validate_items(items)
    assert problems == []
    assert warnings == []
    assert len(items) == 48
    assert sum(it["krio_subset"] for it in items) == 20


def test_validation_catches_errors():
    items = read_jsonl(ITEMS)[:2]
    items[1] = {**items[1], "id": items[0]["id"], "answer": 9}
    problems, _ = validate_items(items)
    assert any("duplicate id" in p for p in problems)
    assert any("answer must be" in p for p in problems)


def test_krio_validation_and_merge():
    items = read_jsonl(ITEMS)
    by_id = {it["id"]: it for it in items}
    flagged = next(it for it in items if it["krio_subset"])
    unflagged = next(it for it in items if not it["krio_subset"])
    good = {"id": flagged["id"], "question": "q", "options": ["a", "b", "c", "d"]}
    assert validate_krio([good], by_id) == []
    assert validate_krio([{**good, "id": unflagged["id"]}], by_id)
    merged = krio_as_items([good], by_id)
    assert merged[0]["answer"] == flagged["answer"]


# ---------- analysis ----------
def rec(model, cond, item_id, rep, chosen, error=None):
    return {
        "model_label": model, "condition": cond, "item_id": item_id, "rep": rep,
        "error": error, "parsed_letter": None if chosen is None else "A",
        "chosen_index": chosen, "correct": chosen == 0, "model_returned": "m-1",
    }


def small_items(n):
    return [{"id": f"T-{i:02d}", "domain": "Test", "question": "q", "options": ["right", "w1", "w2", "w3"], "answer": 0}
            for i in range(n)]


def test_summary_counts_and_audit():
    items = small_items(6)
    records = []
    for i in range(6):
        iid = f"T-{i:02d}"
        for rep in range(3):
            records.append(rec("good", "en", iid, rep, 0))
            for bad in ("b1", "b2", "b3"):
                records.append(rec(bad, "en", iid, rep, 1))
    records.append(rec("good", "en", "T-00", 3, None))
    records.append(rec("good", "en", "T-00", 4, None, error="HTTP 500"))
    s = summarise(records, items, n_boot=500)
    good = s["english"]["good"]
    assert good["accuracy"] < 1.0 and good["accuracy"] > 0.9
    assert good["unparsed_calls"] == 1
    assert good["failed_calls"] == 1
    assert s["english"]["b1"]["accuracy"] == 0.0
    assert len(s["audit"]["consensus_against_key"]) == 6
    assert s["krio"]["good"]["n_items"] == 0


def test_krio_reported_only_with_enough_items():
    n = MIN_KRIO_ITEMS + 1
    items = small_items(n)
    records = []
    for i in range(n):
        iid = f"T-{i:02d}"
        for rep in range(2):
            records.append(rec("m", "en", iid, rep, 0))
            records.append(rec("m", "kri", iid, rep, 0 if i % 2 else 1))
    s = summarise(records, items, n_boot=500)
    assert s["krio"]["m"]["gap"] > 0
    few = [r for r in records if int(r["item_id"][2:]) < MIN_KRIO_ITEMS - 2]
    assert "gap" not in summarise(few, items, n_boot=500)["krio"]["m"]


# ---------- command line ----------
def test_mock_run_stays_out_of_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    common = ["--items", str(ITEMS), "--config", str(CONFIG)]
    assert main(["run", "--run-id", "t", "--mock", "--limit", "4", "--reps", "2", *common]) == 0
    assert list((tmp_path / ".dryrun" / "t").glob("*.jsonl"))
    assert not (tmp_path / "results").exists()
    assert main(["analyse", "--run-id", "t", "--raw-dir", ".dryrun", "--out-dir", ".dryrun/report", *common]) == 0
    report = (tmp_path / ".dryrun" / "report" / "t" / "REPORT.md").read_text(encoding="utf-8")
    assert "DRY RUN" in report


def test_real_run_requires_approved_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    drafts = tmp_path / "drafts.jsonl"
    rows = read_jsonl(ITEMS)
    for r in rows:
        r["status"] = "draft"
    from slheval.data import write_jsonl
    write_jsonl(drafts, rows)
    code = main(["run", "--run-id", "x", "--items", str(drafts), "--config", str(CONFIG)])
    assert code == 2
    assert not (tmp_path / "results").exists()


def test_review_and_krio_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    items_copy = tmp_path / "items.jsonl"
    shutil.copy(ITEMS, items_copy)
    assert main(["review", "--items", str(items_copy), "--approve-all", "--reviewer", "Test Reviewer"]) == 0
    text = items_copy.read_text(encoding="utf-8")
    assert text.startswith("# BENCHMARK DATA SHOULD NOT APPEAR")
    assert all(it["status"] == "reviewed" and it["reviewed_by"] == "Test Reviewer" for it in read_jsonl(items_copy))

    template = tmp_path / "krio.csv"
    assert main(["krio-template", "--items", str(items_copy), "--out", str(template)]) == 0
    import csv
    with template.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 20
    rows[0].update({"question_kri": "k-q", "option_A_kri": "k-a", "option_B_kri": "k-b",
                    "option_C_kri": "k-c", "option_D_kri": "k-d", "translator": "T"})
    with template.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "items_krio.jsonl"
    assert main(["krio-import", str(template), "--items", str(items_copy), "--out", str(out)]) == 0
    imported = read_jsonl(out)
    assert len(imported) == 1 and imported[0]["options"] == ["k-a", "k-b", "k-c", "k-d"]
