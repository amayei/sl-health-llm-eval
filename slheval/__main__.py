"""Command line entry point: python -m slheval <command>."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .analyse import analyse_run
from .data import (
    LETTERS,
    file_sha256,
    krio_as_items,
    read_jsonl,
    status_counts,
    validate_items,
    validate_krio,
    write_jsonl,
)
from .providers import MockProvider, check_models, list_gemini_models, make_provider, runnable
from .run import make_meta, run_model, write_meta
from .stats import DEFAULT_SEED

ITEMS = "data/items.jsonl"
KRIO = "data/items_krio.jsonl"
CONFIG = "config/models.json"


def _load_cfgs(path, wanted):
    cfgs = json.loads(Path(path).read_text(encoding="utf-8"))["models"]
    if wanted:
        labels = {w.strip() for w in wanted.split(",") if w.strip()}
        unknown = labels - {c["label"] for c in cfgs}
        if unknown:
            raise SystemExit(f"unknown model labels: {sorted(unknown)}")
        cfgs = [c for c in cfgs if c["label"] in labels]
    return cfgs


def cmd_validate(a):
    items = read_jsonl(a.items)
    problems, warnings = validate_items(items)
    by_id = {it["id"]: it for it in items}
    if Path(a.krio).exists():
        problems += validate_krio(read_jsonl(a.krio), by_id)
    for w in warnings:
        print("warning:", w)
    for p in problems:
        print("problem:", p)
    print(f"{len(items)} items, status {status_counts(items)}, "
          f"{sum(1 for i in items if i['krio_subset'])} flagged for Krio")
    return 1 if problems else 0


def cmd_review(a):
    items = read_jsonl(a.items)
    if a.list or not (a.approve or a.approve_all):
        print("status:", status_counts(items))
        for it in items:
            if it["status"] != "reviewed":
                print(f"  {it['id']}: {it['question']}")
        return 0
    if not a.reviewer:
        raise SystemExit("--reviewer is required to approve items")
    wanted = {it["id"] for it in items} if a.approve_all else set(a.approve)
    unknown = wanted - {it["id"] for it in items}
    if unknown:
        raise SystemExit(f"unknown ids: {sorted(unknown)}")
    today = datetime.now(timezone.utc).date().isoformat()
    for it in items:
        if it["id"] in wanted:
            it.update({"status": "reviewed", "reviewed_by": a.reviewer, "reviewed_on": today})
    write_jsonl(a.items, items)
    print(f"approved {len(wanted)} items; status now {status_counts(items)}")
    return 0


KRIO_COLUMNS = ["id", "question_en", "option_A_en", "option_B_en", "option_C_en", "option_D_en",
                "question_kri", "option_A_kri", "option_B_kri", "option_C_kri", "option_D_kri",
                "translator", "verified_by"]


def cmd_krio_template(a):
    items = [it for it in read_jsonl(a.items) if it["krio_subset"]]
    with Path(a.out).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(KRIO_COLUMNS)
        for it in items:
            w.writerow([it["id"], it["question"], *it["options"], "", "", "", "", "", "", ""])
    print(f"wrote {a.out} with {len(items)} rows. Keep the option order identical to the English columns.")
    return 0


def cmd_krio_import(a):
    by_id = {it["id"]: it for it in read_jsonl(a.items)}
    rows = []
    with Path(a.csv).open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not (r.get("question_kri") or "").strip():
                continue
            rows.append({
                "id": r["id"],
                "question": r["question_kri"].strip(),
                "options": [(r[f"option_{L}_kri"] or "").strip() for L in LETTERS],
                "translator": (r.get("translator") or "").strip(),
                "verified_by": (r.get("verified_by") or "").strip(),
                "status": "translated",
            })
    problems = validate_krio(rows, by_id)
    if problems:
        print("\n".join(problems))
        return 1
    write_jsonl(a.out, rows)
    print(f"imported {len(rows)} Krio items into {a.out}")
    return 0


def cmd_check_models(a):
    cfgs = _load_cfgs(a.config, a.models)
    ok_any = False
    for label, (ok, detail) in check_models(cfgs).items():
        print(("OK   " if ok else "FAIL ") + f"{label}: {detail}")
        ok_any = ok_any or ok
    return 0 if ok_any else 1


def cmd_list_models(a):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY is not set")
        return 1
    for name in list_gemini_models(key):
        print(name)
    return 0


def cmd_run(a):
    items = read_jsonl(a.items)
    problems, _ = validate_items(items)
    if problems:
        print("\n".join(problems))
        return 2
    drafts = [it["id"] for it in items if it["status"] != "reviewed"]
    if drafts and not (a.allow_drafts or a.mock):
        print(f"{len(drafts)} items are not approved yet. Run `python -m slheval review --list`, "
              "approve them as the author, or pass --allow-drafts for a provisional run.")
        return 2
    by_id = {it["id"]: it for it in items}
    conditions = [("en", items)]
    if not a.no_krio and Path(a.krio).exists():
        krio_rows = read_jsonl(a.krio)
        bad = validate_krio(krio_rows, by_id)
        if bad:
            print("\n".join(bad))
            return 2
        if krio_rows:
            conditions.append(("kri", krio_as_items(krio_rows, by_id)))
    cfgs = _load_cfgs(a.config, a.models)
    if not a.mock:
        skipped = [c["label"] for c in cfgs if not runnable(c)]
        for label in skipped:
            print(f"skipping {label}: API key not set")
        cfgs = [c for c in cfgs if runnable(c)]
    if not cfgs:
        print("no runnable models")
        return 3
    root = Path(".dryrun") if a.mock else Path("results/raw")
    run_dir = root / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    args_dict = {k: v for k, v in vars(a).items() if k != "fn"}
    write_meta(run_dir, make_meta(args_dict, file_sha256(a.items), status_counts(items), cfgs, a.mock))
    for cfg in cfgs:
        provider = MockProvider(cfg["label"]) if a.mock else make_provider(cfg, os.environ[cfg["api_key_env"]])
        print(f"running {cfg['label']} ({cfg['model']})")
        calls, failures = run_model(cfg, provider, conditions, run_dir, a.reps, a.seed, a.limit, a.mock)
        print(f"  done: {calls} new calls, {failures} failed")
    print(f"raw logs in {run_dir}")
    return 0


def cmd_analyse(a):
    items = read_jsonl(a.items)
    raw = Path(a.raw_dir) / a.run_id
    out = Path(a.out_dir) / a.run_id
    analyse_run(raw, out, items)
    print(f"report written to {out / 'REPORT.md'}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="slheval", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--items", default=ITEMS)
        sp.add_argument("--krio", default=KRIO)
        sp.add_argument("--config", default=CONFIG)

    s = sub.add_parser("validate"); common(s); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("review"); common(s)
    s.add_argument("--list", action="store_true")
    s.add_argument("--approve", nargs="*")
    s.add_argument("--approve-all", action="store_true")
    s.add_argument("--reviewer")
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("krio-template"); common(s)
    s.add_argument("--out", default="data/krio_template.csv"); s.set_defaults(fn=cmd_krio_template)
    s = sub.add_parser("krio-import"); common(s)
    s.add_argument("csv"); s.add_argument("--out", default=KRIO); s.set_defaults(fn=cmd_krio_import)
    s = sub.add_parser("check-models"); common(s)
    s.add_argument("--models", default=""); s.set_defaults(fn=cmd_check_models)
    s = sub.add_parser("list-models"); common(s); s.set_defaults(fn=cmd_list_models)
    s = sub.add_parser("run"); common(s)
    s.add_argument("--run-id", required=True)
    s.add_argument("--models", default="")
    s.add_argument("--reps", type=int, default=3)
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.add_argument("--limit", type=int, default=None)
    s.add_argument("--allow-drafts", action="store_true")
    s.add_argument("--no-krio", action="store_true")
    s.add_argument("--mock", action="store_true", help="pipeline test with a fake model; writes to .dryrun/ only")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("analyse"); common(s)
    s.add_argument("--run-id", required=True)
    s.add_argument("--raw-dir", default="results/raw")
    s.add_argument("--out-dir", default="results")
    s.set_defaults(fn=cmd_analyse)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
