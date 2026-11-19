# SL-Health-LLM-Eval

A small, reproducible evaluation of how well general-purpose language models answer practitioner-level public health questions grounded in standard guidance used in Sierra Leone and across West Africa, and whether accuracy drops when the same questions are asked in Krio.

**Status: pilot, version 0.1.** The protocol is fixed before any model result exists. No model results are published here until a real run completes. Results will appear under `results/<run_id>/REPORT.md`.

Author: Alhassan Mayei, PhD candidate in Public Health, Njala University, Sierra Leone. This is an independent pilot. Views are the author's own.

## Why this exists

Health systems in low-resource settings are being offered AI tools that were tested elsewhere. Evaluation evidence from the settings where tools will be used is scarce, and low-resource languages such as Krio are rarely tested at all. This repository is a worked example of a pre-deployment evaluation: a documented construct, an original item bank, a fixed protocol, a transparent harness and honest reporting of uncertainty.

## Research questions

1. **Accuracy.** How accurately do currently available language models answer 48 multiple-choice questions on standard public health guidance (surveillance, Lassa fever, cholera, malaria, maternal and newborn health, child health, infection control, health information)?
2. **Robustness.** How stable are answers when the order of the options changes?
3. **Language gap.** For a 20-item subset translated into Krio, how much does accuracy differ from English on the same items?

An exploratory fourth aim is an answer key audit: flagging items where most models agree on an answer that differs from the key, so that the key and wording can be re-checked.

## Design at a glance

| Element | Choice |
|---|---|
| Items | 48 original multiple-choice questions, 8 domains of 6, four options each |
| Krio subset | 20 items, translated by a native Krio speaker (the author) |
| Prompting | Zero-shot, temperature 0, reply with a letter only |
| Option order | Shuffled with a fixed seed, 3 different orders per item |
| Primary outcome | Mean item-level accuracy, with a 95% bootstrap interval over items |
| Secondary outcomes | Domain accuracy, order consistency, position bias, unparsed rate, English minus Krio gap |
| Inference | Descriptive only. No significance tests |

Full details are in [PROTOCOL.md](PROTOCOL.md). Item construction and known issues are in [DATA_CARD.md](DATA_CARD.md).

## Repository map

```
data/items.jsonl         item bank (with a canary string)
data/items_krio.jsonl    Krio versions, created by `krio-import` once translated
config/models.json       model identifiers and rate limits
slheval/                 harness: prompts, providers, run, analyse, statistics
tests/                   unit and end-to-end tests (pytest)
results/raw/<run_id>/    raw, append-only logs of every model call
results/<run_id>/        report, summary and figures for each run
.github/workflows/       tests on every push; manual evaluation workflow
```

## Reproduce

The harness uses only the Python standard library, plus matplotlib for figures.

```bash
pip install -r requirements.txt
python -m pytest -q
python -m slheval validate

# Pipeline test with a fake model. Writes to .dryrun/ only, never to results/.
python -m slheval run --run-id smoke --mock
python -m slheval analyse --run-id smoke --raw-dir .dryrun --out-dir .dryrun/report

# Real run (needs at least one API key in the environment)
python -m slheval check-models
python -m slheval run --run-id 2026-11-20-run1
python -m slheval analyse --run-id 2026-11-20-run1
```

To run in GitHub Actions instead, add `GEMINI_API_KEY`, `GROQ_API_KEY` or `OPENROUTER_API_KEY` as repository secrets, open the Actions tab, choose **evaluate** and select **Run workflow**. The workflow runs the tests, checks model access, runs the models, writes the report and commits the results.

### Review gate

A real run refuses to start unless every item has been approved by the author:

```bash
python -m slheval review --list
python -m slheval review --approve-all --reviewer "Your Name"
```

Approval is a statement that the author has checked each question, its key and its distractors against current guidance. The gate exists so that unreviewed content cannot produce headline numbers. A provisional run is possible with `--allow-drafts`, and its report carries a warning.

### Krio items

```bash
python -m slheval krio-template     # writes data/krio_template.csv
# fill the question_kri and option_*_kri columns, keeping the English option order
python -m slheval krio-import data/krio_template.csv
```

The English versus Krio comparison is reported only when at least 15 items have results in both languages.

## Results

No real model run has been completed yet. This section will be updated with a link to the first report, whatever it shows.

## Limitations

- Multiple-choice agreement with an answer key measures knowledge of standard guidance. It does not measure clinical competence, safety in practice or usefulness to a health worker.
- Forty-eight items give wide intervals. Expect roughly plus or minus 13 percentage points around an accuracy near 70%, and wider for the 20-item Krio subset.
- Krio medical vocabulary borrows heavily from English. A gap may reflect translation choices as much as model ability. Translation was done by one person and, unless a second reader is recorded in the file, has not been independently back-translated.
- Items follow widely published WHO guidance. Sierra Leone national protocols can differ in detail and should be checked before drawing local conclusions.
- Models change without notice. Each report records the model string returned by the provider and the run date, and is a snapshot.
- Original items may still resemble public material. A canary string is included, but contamination cannot be ruled out.

## Integrity measures

- Protocol committed before any result.
- Review gate on the item bank, with reviewer name and date stored in the data.
- Answer key audit in every report.
- Raw logs are append-only and resumable, with prompt hashes, returned model strings and timestamps.
- Mock runs are isolated in `.dryrun/` and labelled in any report.
- Every completed run is reported, including unfavourable ones.
- Changes to items after the first real run create a new dataset version and a logged deviation.

## AI assistance

The harness code, tests and first draft of the item bank were written with assistance from Claude (Anthropic). The items are drafts until the author approves them through the review gate. The Krio translations, the approval of the answer key and the interpretation of results are the author's own.

## Ethics and safety

No human participants and no patient data are involved. Model outputs in this repository are research artefacts and must not be used for clinical decisions.

## Licence and citation

Code: MIT. Item data: CC BY 4.0, with a request that the data not be included in model training corpora (see the canary string in `data/items.jsonl`).

Cite as: Mayei A. SL-Health-LLM-Eval, version 0.1 (2026). GitHub repository.
