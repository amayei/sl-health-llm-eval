# Architecture

```
Window (pywebview) or browser
        |  HTTP, 127.0.0.1, token header
        v
app/workbench/server.py  (stdlib ThreadingHTTPServer)
        |
        v
slheval  (providers, prompts, run, analyse, stats, data)
        |
        v
config/, data/, results/ (read only)   +   user workspace: runs/, itembanks/
```

## Components

- `slheval`: the evaluation harness. Standard library only. Matplotlib is optional and not bundled in the desktop build.
- `app/workbench/server.py`: JSON API, static file server, job runner (one thread per run), CSV import, HTML export.
- `app/workbench/static/`: single-page interface in plain JavaScript with inline SVG charts.
- `app/main.py`: launcher.
- `packaging/`: PyInstaller spec and Inno Setup script. `.github/workflows/build-windows.yml` builds, tests and smoke-tests on `windows-latest`.

## API

| Method and path | Purpose |
| --- | --- |
| GET /api/state | Runs, banks, models, item status |
| GET /api/items | English and Krio items |
| GET /api/run/{source}/{id} | Run metadata, summary, report text |
| GET /api/export/{source}/{id}.html | Standalone report |
| POST /api/jobs, GET /api/jobs/{id}, POST /api/jobs/{id}/stop | Start, poll, stop a run |
| POST /api/itembanks | Import a CSV or JSONL bank |

All `/api` calls need the `X-Workbench-Token` header.

## Gates mirrored from the CLI

Real runs refuse unapproved items unless the provisional option is set. Mock runs are labelled in metadata and on screen. Run names are validated to prevent path traversal.

## Tests

`python -m pytest -q`. The workbench tests start the server on a random port and cover authentication, host checking, static path safety, the review gate, key handling, import validation, stop, and export.
