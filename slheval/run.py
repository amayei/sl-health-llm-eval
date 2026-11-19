"""Run models over the item bank and write raw, resumable JSONL logs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .data import LETTERS, read_jsonl
from .prompts import (
    SYSTEM_PROMPT,
    build_prompt,
    content_index,
    correct_letter,
    parse_letter,
    permutation,
)


def _git_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def write_meta(run_dir, meta):
    path = Path(run_dir) / "meta.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if existing:
        meta = {**existing, "resumed_utc": meta["started_utc"], "models": meta["models"]}
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def make_meta(args_dict, dataset_sha, status_counts, model_cfgs, mock):
    return {
        "harness_version": __version__,
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "mock": mock,
        "dataset_sha256": dataset_sha,
        "item_status_counts": status_counts,
        "args": args_dict,
        "models": [{k: v for k, v in c.items() if k != "api_key_env"} for c in model_cfgs],
    }


def run_model(cfg, provider, conditions, out_dir, reps, seed, limit=None, mock=False, log=print):
    """conditions: list of (name, items). Appends to <out_dir>/<label>.jsonl and resumes after interruption."""
    label = cfg["label"]
    out_path = Path(out_dir) / f"{label}.jsonl"
    done = set()
    if out_path.exists():
        for rec in read_jsonl(out_path):
            if not rec.get("error"):
                done.add((rec["condition"], rec["item_id"], rec["rep"]))
    pause = 0.0 if mock or not cfg.get("rpm") else 60.0 / float(cfg["rpm"])
    calls = failures = 0
    with out_path.open("a", encoding="utf-8") as fh:
        for rep in range(reps):
            for cond, items in conditions:
                for item in (items[:limit] if limit else items):
                    if (cond, item["id"], rep) in done:
                        continue
                    perm = permutation(item["id"], rep, seed)
                    user = build_prompt(item["question"], item["options"], perm)
                    rec = {
                        "run_mock": mock,
                        "model_label": label,
                        "model_requested": cfg["model"],
                        "provider": cfg["provider"],
                        "item_id": item["id"],
                        "condition": cond,
                        "rep": rep,
                        "perm": perm,
                        "prompt_sha": hashlib.sha256((SYSTEM_PROMPT + user).encode("utf-8")).hexdigest()[:16],
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                    try:
                        out = provider.complete(SYSTEM_PROMPT, user)
                        letter = parse_letter(out["text"])
                        rec.update(
                            {
                                "model_returned": out.get("model_returned"),
                                "raw_response": out["text"],
                                "note": out.get("note"),
                                "parsed_letter": letter,
                                "chosen_index": content_index(letter, perm) if letter else None,
                                "correct_letter": correct_letter(item["answer"], perm),
                                "correct": bool(letter and letter == correct_letter(item["answer"], perm)),
                                "error": None,
                            }
                        )
                    except Exception as err:
                        failures += 1
                        rec.update({"raw_response": None, "parsed_letter": None, "chosen_index": None,
                                    "correct": False, "error": str(err)[:300]})
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    calls += 1
                    if calls % 25 == 0:
                        log(f"  {label}: {calls} calls, {failures} failed")
                    if pause:
                        time.sleep(pause)
    return calls, failures
