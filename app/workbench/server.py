"""Local backend for the SL-Health-LLM-Eval Workbench.

Serves a single-page interface and a small JSON API on 127.0.0.1 only. All analysis reuses the
`slheval` package, so numbers in the app are the numbers in the published reports.

API keys supplied for a run are held in memory for the duration of that run. They are never
written to disk, to run metadata or to logs.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import secrets
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from slheval import __version__ as HARNESS_VERSION
from slheval.analyse import analyse_run
from slheval.data import (
    file_sha256,
    krio_as_items,
    read_jsonl,
    status_counts,
    validate_items,
    validate_krio,
    write_jsonl,
)
from slheval.providers import MockProvider, make_provider
from slheval.run import make_meta, run_model, write_meta
from slheval.stats import DEFAULT_SEED

APP_VERSION = "0.1.5"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
BANK_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,48}$")
MAX_BODY = 5 * 1024 * 1024


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    override = os.environ.get("SLWB_HOME")
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "SL-Health-LLM-Eval-Workbench"
    return Path.home() / ".sl-health-llm-eval-workbench"


class Workbench:
    """State shared by all requests."""

    def __init__(self, root: Path | None = None, work: Path | None = None):
        self.root = Path(root) if root else resource_root()
        self.work = Path(work) if work else workspace_root()
        (self.work / "runs").mkdir(parents=True, exist_ok=True)
        (self.work / "itembanks").mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(24)
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()

    # ----- data access -----
    def items_path(self) -> Path:
        return self.root / "data" / "items.jsonl"

    def krio_path(self) -> Path:
        return self.root / "data" / "items_krio.jsonl"

    def load_items(self):
        return read_jsonl(self.items_path())

    def load_krio(self):
        p = self.krio_path()
        return read_jsonl(p) if p.exists() else []

    def preset_models(self):
        cfg = json.loads((self.root / "config" / "models.json").read_text(encoding="utf-8"))
        return cfg["models"]

    def list_banks(self):
        banks = [{"name": "builtin", "label": "SL-Health-LLM-Eval item bank (48 items)", "n_items": len(self.load_items())}]
        for p in sorted((self.work / "itembanks").glob("*.jsonl")):
            try:
                banks.append({"name": p.stem, "label": f"Custom: {p.stem}", "n_items": len(read_jsonl(p))})
            except Exception:
                continue
        return banks

    def bank_items(self, name):
        if name in (None, "", "builtin"):
            return self.load_items(), True
        if not BANK_NAME_RE.match(name):
            raise ValueError("invalid item bank name")
        path = self.work / "itembanks" / f"{name}.jsonl"
        if not path.exists():
            raise ValueError(f"unknown item bank: {name}")
        return read_jsonl(path), False

    # ----- runs -----
    def _run_dirs(self):
        """Yield (source, run_id, raw_dir, out_dir)."""
        results = self.root / "results"
        if results.exists():
            for d in sorted(results.iterdir()):
                if d.is_dir() and d.name != "raw" and (d / "summary.json").exists():
                    yield "published", d.name, results / "raw" / d.name, d
        runs = self.work / "runs"
        for d in sorted(runs.iterdir()) if runs.exists() else []:
            if (d / "out" / "summary.json").exists():
                yield "local", d.name, d / "raw", d / "out"

    def list_runs(self):
        out = []
        for source, run_id, raw, outd in self._run_dirs():
            meta = self._meta(raw)
            summary = json.loads((outd / "summary.json").read_text(encoding="utf-8"))
            out.append({
                "source": source,
                "id": run_id,
                "started_utc": meta.get("started_utc"),
                "mock": bool(meta.get("mock")),
                "models": summary.get("models", []),
                "item_status": meta.get("item_status_counts", {}),
                "reps": (meta.get("args") or {}).get("reps"),
            })
        out.sort(key=lambda r: r.get("started_utc") or "", reverse=True)
        return out

    @staticmethod
    def _meta(raw: Path) -> dict:
        p = Path(raw) / "meta.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def get_run(self, source, run_id):
        if source not in ("published", "local") or not RUN_ID_RE.match(run_id):
            raise KeyError("run not found")
        for s, rid, raw, outd in self._run_dirs():
            if s == source and rid == run_id:
                return {
                    "source": s,
                    "id": rid,
                    "meta": self._meta(raw),
                    "summary": json.loads((outd / "summary.json").read_text(encoding="utf-8")),
                    "report_md": (outd / "REPORT.md").read_text(encoding="utf-8") if (outd / "REPORT.md").exists() else "",
                }
        raise KeyError("run not found")

    def run_items(self, source, run_id, condition="en"):
        """Per-item, per-model results for the item explorer."""
        if source not in ("published", "local") or not RUN_ID_RE.match(run_id):
            raise KeyError("run not found")
        for s, rid, raw, outd in self._run_dirs():
            if s == source and rid == run_id:
                items = {it["id"]: it for it in self.bank_for_run(raw)}
                models, table = [], {}
                for f in sorted(Path(raw).glob("*.jsonl")):
                    label = f.stem
                    models.append(label)
                    for rec in read_jsonl(f):
                        if rec.get("error") or rec.get("condition") != condition or rec["item_id"] not in items:
                            continue
                        cell = table.setdefault(rec["item_id"], {}).setdefault(label, {"calls": 0, "correct": 0, "picks": [0, 0, 0, 0], "unparsed": 0})
                        cell["calls"] += 1
                        cell["correct"] += 1 if rec.get("correct") else 0
                        if rec.get("chosen_index") is None:
                            cell["unparsed"] += 1
                        else:
                            cell["picks"][rec["chosen_index"]] += 1
                rows = []
                for iid, it in items.items():
                    cells = table.get(iid, {})
                    rows.append({"id": iid, "domain": it["domain"], "question": it["question"], "options": it["options"],
                                 "answer": it["answer"], "models": cells})
                return {"models": models, "items": rows}
        raise KeyError("run not found")

    def bank_for_run(self, raw):
        meta = self._meta(raw)
        bank = (meta.get("args") or {}).get("bank") or "builtin"
        try:
            return self.bank_items(bank)[0]
        except ValueError:
            return self.load_items()

    # ----- item banks -----
    def import_bank(self, name, text, fmt, confirm_reviewed):
        if not BANK_NAME_RE.match(name or ""):
            raise ValueError("Name may use letters, digits, dot, dash and underscore (max 48).")
        rows = parse_bank(text, fmt, confirm_reviewed)
        problems, warnings = validate_items(rows)
        if problems:
            return {"ok": False, "problems": problems[:50], "warnings": warnings}
        write_jsonl(self.work / "itembanks" / f"{name}.jsonl", rows)
        return {"ok": True, "n_items": len(rows), "warnings": warnings}

    # ----- jobs -----
    def start_job(self, params):
        run_id = params.get("run_id") or time.strftime("%Y%m%d-%H%M%S")
        if not RUN_ID_RE.match(run_id):
            raise ValueError("Run name may use letters, digits, dot, dash and underscore.")
        run_dir = self.work / "runs" / run_id
        if run_dir.exists():
            raise ValueError(f"A run named {run_id} already exists. Choose another name.")
        reps = int(params.get("reps", 3))
        if not 1 <= reps <= 10:
            raise ValueError("Repetitions must be between 1 and 10.")
        mock = bool(params.get("mock"))
        items, builtin = self.bank_items(params.get("bank"))
        problems, _ = validate_items(items)
        if problems:
            raise ValueError("Item bank is not valid: " + "; ".join(problems[:5]))
        drafts = [it["id"] for it in items if it["status"] != "reviewed"]
        allow_drafts = bool(params.get("allow_drafts"))
        if drafts and not (allow_drafts or mock):
            raise ValueError(f"{len(drafts)} items are not approved. Approve them, or tick the provisional run option.")
        models = self._resolve_models(params.get("models") or [], mock)
        if not models:
            raise ValueError("Select at least one model, and enter its API key.")
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "run_id": run_id, "n_models": len(models), "status": "running", "log": [], "progress": {}, "error": None,
               "started": time.time(), "stop": False}
        with self.lock:
            self.jobs[job_id] = job
        threading.Thread(target=self._run_job, args=(job, params, items, builtin, models, reps, mock, allow_drafts),
                         daemon=True).start()
        return {"job_id": job_id, "run_id": run_id}

    def _resolve_models(self, selected, mock):
        presets = {m["label"]: m for m in self.preset_models()}
        resolved = []
        for sel in selected:
            key = (sel.get("api_key") or "").strip()
            if sel.get("custom"):
                cfg = {"label": sel["label"], "provider": "custom", "model": sel["model"], "base_url": sel["base_url"],
                       "max_tokens": int(sel.get("max_tokens", 16)), "rpm": sel.get("rpm")}
                if not re.match(r"^[A-Za-z0-9._-]{1,48}$", cfg["label"]):
                    raise ValueError("Custom model label may use letters, digits, dot, dash and underscore.")
            else:
                if sel["label"] not in presets:
                    raise ValueError(f"unknown model {sel['label']}")
                cfg = dict(presets[sel["label"]])
                if not key and not mock:
                    raise ValueError(f"Enter the API key for {cfg['label']}.")
            resolved.append((cfg, key))
        return resolved

    def _run_job(self, job, params, items, builtin, models, reps, mock, allow_drafts):
        def log(msg):
            job["log"].append(f"{time.strftime('%H:%M:%S')} {msg}")
        run_dir = self.work / "runs" / job["run_id"]
        raw = run_dir / "raw"
        try:
            raw.mkdir(parents=True)
            by_id = {it["id"]: it for it in items}
            conditions = [("en", items)]
            if builtin and params.get("include_krio", True) and self.krio_path().exists():
                krio_rows = self.load_krio()
                bad = validate_krio(krio_rows, by_id)
                if bad:
                    raise ValueError("Krio data is not valid: " + "; ".join(bad[:3]))
                if krio_rows:
                    conditions.append(("kri", krio_as_items(krio_rows, by_id)))
            sha = hashlib.sha256(json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()
            args = {"run_id": job["run_id"], "reps": reps, "seed": DEFAULT_SEED, "mock": mock,
                    "allow_drafts": allow_drafts, "bank": params.get("bank") or "builtin", "source": "workbench"}
            clean_cfgs = [{k: v for k, v in c.items() if k != "api_key_env"} for c, _ in models]
            write_meta(raw, make_meta(args, sha, status_counts(items), clean_cfgs, mock))
            limit = params.get("limit")
            limit = int(limit) if limit else None
            job["expected"] = sum(len(its[:limit] if limit else its) for _, its in conditions) * reps
            for cfg, key in models:
                if job["stop"]:
                    break
                provider = MockProvider(cfg["label"]) if mock else make_provider(cfg, key)
                log(f"Running {cfg['label']} ({cfg['model']})")

                def progress(label, calls, failures):
                    job["progress"][label] = {"calls": calls, "failures": failures}

                calls, failures = run_model(cfg, provider, conditions, raw, reps, DEFAULT_SEED, limit, mock,
                                            log=log, should_stop=lambda: job["stop"], progress=progress)
                log(f"  {cfg['label']}: {calls} calls, {failures} failed")
            if job["stop"]:
                job["status"] = "stopped"
                log("Stopped. Partial raw logs are kept but no report was produced.")
                return
            if not any(raw.glob("*.jsonl")):
                raise ValueError("No results were recorded.")
            log("Analysing")
            analyse_run(raw, run_dir / "out", items)
            job["status"] = "done"
            log("Done")
        except (Exception, SystemExit) as err:  # surface any failure to the interface
            job["status"] = "failed"
            job["error"] = str(err)[:500]
            log(f"Failed: {job['error']}")

    def job_view(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError("job not found")
        view = {k: job[k] for k in ("id", "run_id", "status", "log", "progress", "error")}
        view["expected"] = job.get("expected")
        view["n_models"] = job.get("n_models")
        return view

    def stop_job(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError("job not found")
        job["stop"] = True
        return {"ok": True}


def clean_nan(obj):
    """JSON has no NaN. Replace NaN and infinity with null before sending to the browser."""
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj


# ----- item bank parsing -----
def parse_bank(text, fmt, confirm_reviewed):
    """Accept JSONL in harness format, or CSV with id,domain,question,option_a..d,answer."""
    rows = []
    if fmt == "jsonl":
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(json.loads(line))
    elif fmt == "csv":
        for r in csv.DictReader(io.StringIO(text)):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            opts = [r.get(f"option_{c}", "") for c in "abcd"]
            ans = r.get("answer", "")
            if ans.upper() in list("ABCD"):
                ans_i = "ABCD".index(ans.upper())
            elif ans.isdigit():
                ans_i = int(ans)
            else:
                ans_i = -1
            rows.append({"id": r.get("id", ""), "domain": r.get("domain", "General"), "question": r.get("question", ""),
                         "options": opts, "answer": ans_i})
    else:
        raise ValueError("Format must be jsonl or csv.")
    status = "reviewed" if confirm_reviewed else "draft"
    for r in rows:
        r.setdefault("source_anchor", "user-supplied")
        r.setdefault("krio_subset", False)
        r["status"] = status
    return rows


# ----- report export -----
def md_to_html(md: str) -> str:
    """Small renderer for the constructs produced by slheval.analyse.render_report."""
    def inline(t):
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        return t
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.startswith("> "):
            out.append(f"<blockquote>{inline(ln[2:])}</blockquote>")
        elif ln.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            i -= 1
            cells = [[c.strip() for c in b.strip().strip("|").split("|")] for b in block if not re.match(r"^\|[-| ]+\|$", b)]
            if cells:
                out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells[0]) + "</tr></thead><tbody>")
                for r in cells[1:]:
                    out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
                out.append("</tbody></table>")
        elif ln.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                out.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            i -= 1
            out.append("</ul>")
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def export_csv(run) -> str:
    """Long-format results for analysts: one row per model and scope."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["run_id", "model", "scope", "domain", "n_items", "accuracy", "ci_low", "ci_high", "order_consistency",
                "unparsed_rate", "failed_calls", "mock", "harness_version"])
    meta = run["meta"]
    tail = [bool(meta.get("mock")), meta.get("harness_version", "")]
    for model, m in run["summary"]["english"].items():
        w.writerow([run["id"], model, "overall", "", m["n_items"], m["accuracy"], m["ci_low"], m["ci_high"], m.get("consistency"),
                    m.get("unparsed_rate"), m.get("failed_calls"), *tail])
        for dom, d in sorted((m.get("domain_accuracy") or {}).items()):
            w.writerow([run["id"], model, "domain", dom, d["n_items"], d["accuracy"], "", "", "", "", "", *tail])
    for model, k in (run["summary"].get("krio") or {}).items():
        w.writerow([run["id"], model, "krio_en_paired", "", k["n_items"], k.get("en_accuracy"), "", "", "", "", "", *tail])
        w.writerow([run["id"], model, "krio_kri_paired", "", k["n_items"], k.get("kri_accuracy"), "", "", "", "", "", *tail])
        w.writerow([run["id"], model, "krio_gap_en_minus_kri", "", k["n_items"], k.get("gap"), k.get("ci_low"), k.get("ci_high"), "", "", "", *tail])
    return out.getvalue()


def export_html(run) -> str:
    meta = run["meta"]
    banner = ""
    if meta.get("mock"):
        banner = '<p class="warn">SIMULATED RESULTS from a mock model. Not real evaluation data.</p>'
    css = ("body{font-family:Arial,Helvetica,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1b2733}"
           "table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.9rem}th,td{border:1px solid #c9d3dd;padding:.4rem .6rem;text-align:left}"
           "th{background:#e8eef4}blockquote{border-left:4px solid #b26a00;background:#fff4e0;margin:1rem 0;padding:.6rem 1rem}"
           ".warn{background:#fbe3e3;border-left:4px solid #b00020;padding:.6rem 1rem;font-weight:bold}code{background:#eef2f6;padding:0 .2rem}")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Evaluation report {html.escape(run['id'])}</title>"
            f"<style>{css}</style></head><body>{banner}{md_to_html(run['report_md'])}"
            f"<hr><p><small>Exported from SL-Health-LLM-Eval Workbench {APP_VERSION}, harness {HARNESS_VERSION}.</small></p></body></html>")


# ----- HTTP layer -----
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}


def make_handler(wb: Workbench, port_holder):
    static_dir = Path(__file__).resolve().parent / "static"
    if getattr(sys, "frozen", False):
        static_dir = resource_root() / "workbench" / "static"

    class Handler(BaseHTTPRequestHandler):
        server_version = "SLWB"

        def log_message(self, fmt, *args):  # quiet, and never log request bodies
            pass

        # -- helpers --
        def _host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(clean_nan(body), ensure_ascii=False, allow_nan=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            return secrets.compare_digest(self.headers.get("X-Workbench-Token", ""), wb.token)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("Request too large.")
            return json.loads(self.rfile.read(n) or b"{}")

        # -- routes --
        def do_GET(self):
            if not self._host_ok():
                return self._send(HTTPStatus.FORBIDDEN, {"error": "bad host"})
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._static(path)
            if not self._authed():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "missing token"})
            try:
                if path == "/api/state":
                    items = wb.load_items()
                    return self._send(200, {
                        "app_version": APP_VERSION, "harness_version": HARNESS_VERSION,
                        "runs": wb.list_runs(), "banks": wb.list_banks(),
                        "item_status": status_counts(items), "n_krio": len(wb.load_krio()),
                        "models": [{"label": m["label"], "provider": m["provider"], "model": m["model"],
                                    "key_name": m["api_key_env"]} for m in wb.preset_models()],
                        "workspace": str(wb.work)})
                if path == "/api/items":
                    return self._send(200, {"items": wb.load_items(), "krio": wb.load_krio()})
                m = re.match(r"^/api/run/(published|local)/([^/]+)$", path)
                if m:
                    return self._send(200, wb.get_run(m.group(1), unquote(m.group(2))))
                m = re.match(r"^/api/run/(published|local)/([^/]+)/items$", path)
                if m:
                    q = parse_qs(urlparse(self.path).query)
                    return self._send(200, wb.run_items(m.group(1), unquote(m.group(2)), (q.get("condition") or ["en"])[0]))
                m = re.match(r"^/api/export/(published|local)/([^/]+)\.csv$", path)
                if m:
                    run = wb.get_run(m.group(1), unquote(m.group(2)))
                    return self._send(200, export_csv(clean_nan(run)), "text/csv; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="results-{run["id"]}.csv"'})
                m = re.match(r"^/api/export/(published|local)/([^/]+)\.html$", path)
                if m:
                    run = wb.get_run(m.group(1), unquote(m.group(2)))
                    return self._send(200, export_html(run), "text/html; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="report-{run["id"]}.html"'})
                m = re.match(r"^/api/jobs/([a-f0-9]+)$", path)
                if m:
                    return self._send(200, wb.job_view(m.group(1)))
            except KeyError as err:
                return self._send(404, {"error": str(err)})
            except Exception as err:
                return self._send(400, {"error": str(err)})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(HTTPStatus.FORBIDDEN, {"error": "bad host"})
            if not self._authed():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "missing token"})
            path = urlparse(self.path).path
            try:
                body = self._body()
                if path == "/api/jobs":
                    return self._send(200, wb.start_job(body))
                m = re.match(r"^/api/jobs/([a-f0-9]+)/stop$", path)
                if m:
                    return self._send(200, wb.stop_job(m.group(1)))
                if path == "/api/itembanks":
                    return self._send(200, wb.import_bank(body.get("name"), body.get("text", ""), body.get("format", "csv"),
                                                          bool(body.get("confirm_reviewed"))))
            except KeyError as err:
                return self._send(404, {"error": str(err)})
            except (ValueError, json.JSONDecodeError) as err:
                return self._send(400, {"error": str(err)})
            return self._send(404, {"error": "not found"})

        def _static(self, path):
            if path in ("/", "/index.html"):
                page = (static_dir / "index.html").read_text(encoding="utf-8")
                page = page.replace("__WB_TOKEN__", wb.token).replace("__APP_VERSION__", APP_VERSION)
                return self._send(200, page, STATIC_TYPES[".html"])
            rel = path.lstrip("/")
            target = (static_dir / rel).resolve()
            if static_dir.resolve() not in target.parents or not target.is_file():
                return self._send(404, {"error": "not found"})
            return self._send(200, target.read_bytes(), STATIC_TYPES.get(target.suffix, "application/octet-stream"))

    return Handler


def serve(wb: Workbench | None = None, port: int = 0):
    wb = wb or Workbench()
    holder = {}
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(wb, holder))
    holder["port"] = httpd.server_address[1]
    return wb, httpd
