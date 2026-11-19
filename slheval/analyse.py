"""Score raw logs and write the report. Descriptive statistics only, no significance claims."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .data import LETTERS, read_jsonl
from .stats import bootstrap_ci, mean

MIN_KRIO_ITEMS = 15
N_BOOT = 10000


def load_records(run_dir):
    """Read every JSONL log in a run directory. For repeated (model, condition, item, rep) keys the last line wins."""
    latest = {}
    for path in sorted(Path(run_dir).glob("*.jsonl")):
        for rec in read_jsonl(path):
            latest[(rec["model_label"], rec["condition"], rec["item_id"], rec["rep"])] = rec
    return list(latest.values())


def group(records):
    grouped = defaultdict(lambda: defaultdict(list))
    for rec in records:
        grouped[(rec["model_label"], rec["condition"])][rec["item_id"]].append(rec)
    return grouped


def summarise_condition(by_item, items_by_id, n_boot=N_BOOT):
    rates, domain_rates = {}, defaultdict(list)
    unparsed = failed = valid_calls = 0
    letters, consistency = Counter(), []
    for item_id, recs in by_item.items():
        failed += sum(1 for r in recs if r.get("error"))
        valid = [r for r in recs if not r.get("error")]
        if not valid or item_id not in items_by_id:
            continue
        rate = sum(1 for r in valid if r["correct"]) / len(valid)
        rates[item_id] = rate
        domain_rates[items_by_id[item_id]["domain"]].append(rate)
        valid_calls += len(valid)
        unparsed += sum(1 for r in valid if r.get("parsed_letter") is None)
        letters.update(r["parsed_letter"] for r in valid if r.get("parsed_letter"))
        chosen = [r["chosen_index"] for r in valid if r.get("chosen_index") is not None]
        if len(chosen) >= 2:
            consistency.append(Counter(chosen).most_common(1)[0][1] / len(chosen))
    parsed_total = sum(letters.values())
    lo, hi = bootstrap_ci(rates.values(), n_boot=n_boot)
    return {
        "n_items": len(rates),
        "accuracy": mean(rates.values()),
        "ci_low": lo,
        "ci_high": hi,
        "valid_calls": valid_calls,
        "unparsed_calls": unparsed,
        "unparsed_rate": unparsed / valid_calls if valid_calls else float("nan"),
        "failed_calls": failed,
        "consistency": mean(consistency),
        "letter_counts": {k: letters.get(k, 0) for k in LETTERS},
        "top_letter_share": max(letters.values()) / parsed_total if parsed_total else float("nan"),
        "domain_accuracy": {d: {"accuracy": mean(v), "n_items": len(v)} for d, v in domain_rates.items()},
        "item_rates": rates,
    }


def modal_choice(recs):
    chosen = [r["chosen_index"] for r in recs if not r.get("error") and r.get("chosen_index") is not None]
    if not chosen:
        return None
    top = Counter(chosen).most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1]:
        return None
    return top[0][0]


def key_audit(grouped, items_by_id, min_models=3, agree_share=0.75):
    """Flag items where most models converge on one non-key answer, and items no model ever gets right."""
    models = sorted({m for (m, c) in grouped if c == "en"})
    flagged, never_correct = [], []
    for item_id, item in items_by_id.items():
        picks, rates = [], []
        for m in models:
            recs = grouped[(m, "en")].get(item_id, [])
            if not recs:
                continue
            picks.append(modal_choice(recs))
            valid = [r for r in recs if not r.get("error")]
            if valid:
                rates.append(sum(1 for r in valid if r["correct"]) / len(valid))
        if len(rates) >= min_models and all(r == 0 for r in rates):
            never_correct.append(item_id)
        if len(picks) >= min_models:
            top = Counter(p for p in picks if p is not None).most_common(1)
            if top and top[0][0] != item["answer"] and top[0][1] / len(picks) >= agree_share:
                flagged.append(
                    {
                        "id": item_id,
                        "key": item["options"][item["answer"]],
                        "consensus": item["options"][top[0][0]],
                        "models_agreeing": top[0][1],
                        "models": len(picks),
                    }
                )
    return {"consensus_against_key": flagged, "never_correct": never_correct}


def krio_comparison(grouped, models, n_boot=N_BOOT):
    out = {}
    for m in models:
        en, kri = grouped.get((m, "en"), {}), grouped.get((m, "kri"), {})
        diffs, en_rates, kri_rates = [], [], []
        for item_id in sorted(set(en) & set(kri)):
            e = [r for r in en[item_id] if not r.get("error")]
            k = [r for r in kri[item_id] if not r.get("error")]
            if not e or not k:
                continue
            er = sum(1 for r in e if r["correct"]) / len(e)
            kr = sum(1 for r in k if r["correct"]) / len(k)
            en_rates.append(er)
            kri_rates.append(kr)
            diffs.append(er - kr)
        if len(diffs) >= MIN_KRIO_ITEMS:
            lo, hi = bootstrap_ci(diffs, n_boot=n_boot)
            out[m] = {"n_items": len(diffs), "en_accuracy": mean(en_rates), "kri_accuracy": mean(kri_rates),
                      "gap": mean(diffs), "ci_low": lo, "ci_high": hi}
        else:
            out[m] = {"n_items": len(diffs), "reported": False}
    return out


def summarise(records, items, n_boot=N_BOOT):
    items_by_id = {it["id"]: it for it in items}
    grouped = group(records)
    models = sorted({m for (m, _c) in grouped})
    returned = defaultdict(set)
    for r in records:
        if r.get("model_returned"):
            returned[r["model_label"]].add(r["model_returned"])
    per_model = {m: summarise_condition(grouped[(m, "en")], items_by_id, n_boot) for m in models if (m, "en") in grouped}
    return {
        "models": models,
        "model_returned": {m: sorted(v) for m, v in returned.items()},
        "english": per_model,
        "krio": krio_comparison(grouped, models, n_boot),
        "audit": key_audit(grouped, items_by_id),
    }


def pct(x):
    return "n/a" if x != x else f"{100 * x:.1f}%"


def render_report(summary, meta, items):
    en = summary["english"]
    lines = ["# Evaluation report", ""]
    if meta.get("mock"):
        lines += ["> **DRY RUN WITH A MOCK MODEL. These numbers are meaningless and must not be cited.**", ""]
    counts = meta.get("item_status_counts", {})
    if counts.get("draft"):
        lines += [f"> Item bank includes {counts['draft']} items not yet approved by the author. Treat results as provisional.", ""]
    lines += [
        "## Run details",
        "",
        f"- Run started (UTC): {meta.get('started_utc')}",
        f"- Harness version: {meta.get('harness_version')}, commit: {meta.get('git_commit')}",
        f"- Dataset SHA-256: `{meta.get('dataset_sha256')}`",
        f"- Item status: {counts}",
        f"- Repetitions per item and condition: {meta.get('args', {}).get('reps')}",
        "",
        "## English accuracy (primary outcome)",
        "",
        "Mean item-level accuracy over shuffled option orders. The 95% interval is a percentile bootstrap over items (10,000 resamples). Chance is 25%.",
        "",
        "| Model | Model string returned | Items | Accuracy | 95% CI | Unparsed | Failed calls | Order consistency | Top letter share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m, s in en.items():
        returned = ", ".join(summary["model_returned"].get(m, [])) or "unknown"
        lines.append(
            f"| {m} | {returned} | {s['n_items']} | {pct(s['accuracy'])} | {pct(s['ci_low'])} to {pct(s['ci_high'])} | "
            f"{pct(s['unparsed_rate'])} | {s['failed_calls']} | {pct(s['consistency'])} | {pct(s['top_letter_share'])} |"
        )
    domains = []
    for it in items:
        if it["domain"] not in domains:
            domains.append(it["domain"])
    lines += ["", "## Accuracy by domain", "", "Six items per domain, so these are descriptive only.", ""]
    lines.append("| Domain | " + " | ".join(en) + " |")
    lines.append("|---|" + "---|" * len(en))
    for d in domains:
        cells = [pct(s["domain_accuracy"].get(d, {}).get("accuracy", float("nan"))) for s in en.values()]
        lines.append(f"| {d} | " + " | ".join(cells) + " |")
    lines += ["", "## English versus Krio", ""]
    reported = {m: k for m, k in summary["krio"].items() if k.get("reported", True) and "gap" in k}
    if reported:
        lines += [
            f"Paired comparison on items with both versions (minimum {MIN_KRIO_ITEMS} items). Gap is English minus Krio accuracy.",
            "",
            "| Model | Items | English | Krio | Gap | 95% CI of gap |",
            "|---|---|---|---|---|---|",
        ]
        for m, k in reported.items():
            lines.append(
                f"| {m} | {k['n_items']} | {pct(k['en_accuracy'])} | {pct(k['kri_accuracy'])} | "
                f"{100 * k['gap']:+.1f} points | {100 * k['ci_low']:+.1f} to {100 * k['ci_high']:+.1f} |"
            )
    else:
        lines.append(f"Not reported: fewer than {MIN_KRIO_ITEMS} items have both English and Krio results.")
    audit = summary["audit"]
    lines += ["", "## Answer key audit", "",
              "Items where most models agree on an answer that differs from the key. These need author review: either the key or the item wording may be wrong.", ""]
    if audit["consensus_against_key"]:
        lines += ["| Item | Key | Model consensus | Models agreeing |", "|---|---|---|---|"]
        for f in audit["consensus_against_key"]:
            lines.append(f"| {f['id']} | {f['key']} | {f['consensus']} | {f['models_agreeing']} of {f['models']} |")
    else:
        lines.append("No items flagged.")
    lines += ["", "Items no model answered correctly: " + (", ".join(audit["never_correct"]) or "none") + ".", ""]
    lines += [
        "## How to read this report",
        "",
        "- Scores measure agreement with an author-reviewed key on standard public health guidance. They do not measure clinical competence or safety.",
        "- Intervals are wide because the item bank is small. See PROTOCOL.md for what this study can and cannot show.",
        "- Model versions change. These results are a dated snapshot.",
        "",
    ]
    return "\n".join(lines)


def make_figures(summary, out_dir):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    en = summary["english"]
    if en:
        fig, ax = plt.subplots(figsize=(7, 0.7 * len(en) + 1.8))
        labels = list(en)
        acc = [100 * en[m]["accuracy"] for m in labels]
        err_lo = [100 * (en[m]["accuracy"] - en[m]["ci_low"]) for m in labels]
        err_hi = [100 * (en[m]["ci_high"] - en[m]["accuracy"]) for m in labels]
        ax.barh(labels, acc, xerr=[err_lo, err_hi], color="#1f6f8b", capsize=3)
        ax.axvline(25, color="#999999", linestyle="--", linewidth=1)
        ax.text(25.5, -0.45, "chance", color="#666666", fontsize=8)
        ax.set_xlim(0, 100)
        ax.set_xlabel("Accuracy on English items (%), 95% bootstrap CI")
        ax.set_title("Accuracy by model")
        fig.tight_layout()
        p = out_dir / "accuracy_by_model.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        paths.append(p)
    kri = {m: k for m, k in summary["krio"].items() if "gap" in k}
    if kri:
        fig, ax = plt.subplots(figsize=(7, 4))
        labels = list(kri)
        x = range(len(labels))
        ax.bar([i - 0.2 for i in x], [100 * kri[m]["en_accuracy"] for m in labels], 0.4, label="English", color="#1f6f8b")
        ax.bar([i + 0.2 for i in x], [100 * kri[m]["kri_accuracy"] for m in labels], 0.4, label="Krio", color="#d98e04")
        ax.axhline(25, color="#999999", linestyle="--", linewidth=1)
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_ylabel("Accuracy (%) on shared items")
        ax.set_title("English versus Krio")
        ax.legend()
        fig.tight_layout()
        p = out_dir / "english_vs_krio.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        paths.append(p)
    return paths


def analyse_run(raw_dir, out_dir, items, n_boot=N_BOOT):
    records = load_records(raw_dir)
    if not records:
        raise SystemExit(f"no records found in {raw_dir}")
    meta_path = Path(raw_dir) / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    summary = summarise(records, items, n_boot)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = make_figures(summary, out_dir / "figures")
    report = render_report(summary, meta, items)
    if figures:
        report += "\n## Figures\n\n" + "\n".join(f"![{p.stem}](figures/{p.name})" for p in figures) + "\n"
    slim = json.loads(json.dumps(summary, default=str))
    for s in slim["english"].values():
        s.pop("item_rates", None)
    (out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return summary
