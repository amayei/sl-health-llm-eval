import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from app.workbench.server import Workbench, clean_nan, export_html, md_to_html, parse_bank, serve


@pytest.fixture()
def server(tmp_path):
    wb, httpd = serve(Workbench(work=tmp_path))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield wb, httpd.server_address[1]
    httpd.shutdown()


def call(port, path, token=None, body=None, host=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Workbench-Token"] = token
    if host:
        headers["Host"] = host
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def wait(wb, job_id, seconds=60):
    for _ in range(seconds * 4):
        v = wb.job_view(job_id)
        if v["status"] != "running":
            return v
        time.sleep(0.25)
    raise AssertionError("job did not finish")


def test_api_requires_token(server):
    wb, port = server
    assert call(port, "/api/state")[0] == 401
    assert call(port, "/api/state", token="wrong")[0] == 401
    assert call(port, "/api/state", token=wb.token)[0] == 200


def test_rejects_foreign_host_header(server):
    wb, port = server
    assert call(port, "/api/state", token=wb.token, host="evil.example")[0] == 403


def test_index_has_token_but_static_traversal_blocked(server):
    wb, port = server
    code, body = call(port, "/")
    assert code == 200 and wb.token.encode() in body
    assert call(port, "/..%2f..%2fserver.py")[0] == 404
    assert call(port, "/../server.py")[0] in (404, 400)


def test_real_run_refuses_unapproved_items(server):
    wb, port = server
    with pytest.raises(ValueError, match="not approved"):
        wb.start_job({"run_id": "r1", "models": [{"label": "gemini-flash", "api_key": "k"}]})


def test_real_run_needs_key(server):
    wb, _ = server
    with pytest.raises(ValueError, match="API key"):
        wb.start_job({"run_id": "r2", "allow_drafts": True, "models": [{"label": "gemini-flash"}]})


def test_mock_run_end_to_end_and_no_key_persisted(server):
    wb, port = server
    r = wb.start_job({"run_id": "m1", "reps": 2, "mock": True, "models": [{"label": "gemini-flash"}, {"label": "gemma-31b-gemini"}, {"label": "llama-70b-groq"}]})
    v = wait(wb, r["job_id"])
    assert v["status"] == "done", v
    code, body = call(port, "/api/run/local/m1", token=wb.token)
    run = json.loads(body)
    assert code == 200 and run["meta"]["mock"] is True
    assert run["summary"]["english"]["gemini-flash"]["n_items"] == 48
    code, body = call(port, "/api/export/local/m1.html", token=wb.token)
    assert b"SIMULATED RESULTS" in body
    assert call(port, "/api/run/local/..%2f..", token=wb.token)[0] == 404


def test_api_key_never_written(server):
    wb, _ = server
    secret = "SECRET-KEY-VALUE-123"
    r = wb.start_job({"run_id": "k1", "reps": 1, "mock": True, "models": [{"label": "gemini-flash", "api_key": secret}]})
    wait(wb, r["job_id"])
    for p in wb.work.rglob("*"):
        if p.is_file():
            assert secret.encode() not in p.read_bytes()
    assert secret not in json.dumps(wb.job_view(r["job_id"]))


def test_duplicate_run_name_rejected(server):
    wb, _ = server
    r = wb.start_job({"run_id": "d1", "reps": 1, "mock": True, "models": [{"label": "gemini-flash"}]})
    wait(wb, r["job_id"])
    with pytest.raises(ValueError, match="already exists"):
        wb.start_job({"run_id": "d1", "reps": 1, "mock": True, "models": [{"label": "gemini-flash"}]})


def test_stop_job(server):
    wb, _ = server
    r = wb.start_job({"run_id": "s1", "reps": 10, "mock": True, "models": [{"label": "gemini-flash"}]})
    wb.stop_job(r["job_id"])
    assert wait(wb, r["job_id"])["status"] in ("stopped", "done")


def test_import_bank_csv_and_validation(server):
    wb, _ = server
    ok = "id,domain,question,option_a,option_b,option_c,option_d,answer\nQ1,Test,What?,a,b,c,d,B\nQ2,Test,Why?,w,x,y,z,D\n"
    res = wb.import_bank("mybank", ok, "csv", False)
    assert res["ok"] and res["n_items"] == 2
    assert {b["name"] for b in wb.list_banks()} == {"builtin", "mybank"}
    items, builtin = wb.bank_items("mybank")
    assert not builtin and items[0]["answer"] == 1 and items[0]["status"] == "draft"
    bad = "id,domain,question,option_a,option_b,option_c,option_d,answer\nQ1,Test,What?,a,a,c,d,B\n"
    assert not wb.import_bank("badbank", bad, "csv", False)["ok"]
    with pytest.raises(ValueError):
        wb.import_bank("../escape", ok, "csv", False)


def test_reviewed_bank_runs_without_draft_flag_in_mock_free_mode(server):
    wb, _ = server
    ok = "id,domain,question,option_a,option_b,option_c,option_d,answer\n" + "".join(f"Q{i},T,Q{i}?,a,b,c,d,A\n" for i in range(5))
    wb.import_bank("rev", ok, "csv", True)
    items, _ = wb.bank_items("rev")
    assert all(i["status"] == "reviewed" for i in items)


def test_clean_nan_and_markdown():
    assert clean_nan({"a": float("nan"), "b": [1.0, float("inf")]}) == {"a": None, "b": [1.0, None]}
    html = md_to_html("# T\n\n| a | b |\n|---|---|\n| 1 | <x> |\n")
    assert "<table>" in html and "&lt;x&gt;" in html
    assert "SIMULATED" in export_html({"id": "x", "meta": {"mock": True}, "report_md": "# R"})


def test_parse_bank_rejects_unknown_format():
    with pytest.raises(ValueError):
        parse_bank("x", "xml", False)
