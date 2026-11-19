# Evaluation protocol

Version 0.1, dated 2026-11-19. This document was committed before any model result existed. Later changes are recorded in the deviations log at the end, with date and reason.

## 1. Purpose

To estimate how accurately current general-purpose language models answer practitioner-level public health questions on standard guidance relevant to Sierra Leone, how stable those answers are, and whether performance differs between English and Krio. The study is a pilot intended to demonstrate a transparent pre-deployment evaluation method, not to rank models.

## 2. Construct

**Measured:** agreement with an author-reviewed key on recall and simple application of widely published public health guidance.

**Not measured:** clinical reasoning in realistic cases, safety of free-text advice, calibration, usefulness to health workers, or fairness across patient groups.

Threats to construct validity, stated in advance:

- Multiple-choice format allows elimination strategies that real tasks do not.
- Items test guidance as published by international bodies. National protocols may differ.
- Krio items test the translation as well as the model.
- Items were drafted with AI assistance, so they may resemble the style of model-generated text.

## 3. Materials

- **Item bank:** 48 original items, 8 domains with 6 items each, 4 options, one correct. Correct answers are balanced across positions A to D (12 each) in the file. Each item has a topic-level source anchor.
- **Krio subset:** 20 items flagged in the item bank, translated into Krio by the author. Option order matches the English file.
- **Models:** those listed in `config/models.json` that are reachable with free-tier keys on the run date. The exact model string returned by each provider is recorded.

## 4. Procedure

1. The author reviews every item and approves it (`slheval review`). Real runs refuse to start otherwise.
2. For each model, condition (English, Krio), item and repetition `r` in {0, 1, 2}, options are shuffled with a seeded permutation derived from the item identifier and `r`. The same seed is used for every model.
3. Each prompt contains a fixed system instruction and the question with four lettered options. Temperature is 0. No examples are given.
4. A reply is parsed strictly. A single letter, a letter followed by punctuation, or an explicit statement such as "the answer is B" is accepted. Anything else is unparsed.
5. Unparsed replies are scored incorrect and counted. Calls that fail at the API level are excluded from accuracy and reported as failed calls. Failed calls are retried when a run is resumed.
6. Every call is logged to an append-only JSONL file with item, condition, repetition, option order, prompt hash, raw reply, returned model string and timestamp.

## 5. Outcomes and analysis

**Primary outcome.** For each model, the mean over items of the proportion of repetitions answered correctly (English condition), with a 95% percentile bootstrap interval from 10,000 resamples of items (seed 20261119). Chance level is 25%.

**Secondary outcomes.**

- Accuracy by domain, descriptive only because each domain has 6 items.
- Order consistency: for each item, the share of repetitions that select the same option content, averaged over items.
- Position bias: share of replies choosing each displayed letter, and the share of the most chosen letter.
- Unparsed rate and failed-call count.
- English minus Krio accuracy gap on items with results in both conditions, with a paired bootstrap interval over items. Reported only if at least 15 items have both. Otherwise the report states that it is not reported.

**Answer key audit (exploratory).** Items where at least 75% of models, with a minimum of three, converge on the same option that differs from the key, and items that no model answers correctly. These are flagged for author review and are not used to change scores in the run that produced them.

**Inference.** Estimates and intervals only. No hypothesis tests and no claims of ranking between models whose intervals overlap.

## 6. Precision

With 48 items and an accuracy near 70%, the standard error is about 0.066 and a 95% interval spans roughly 26 percentage points. With 20 items the interval is wider, roughly 40 points, and a paired gap interval will be narrower only to the extent that item difficulty is shared across languages. Differences smaller than about 15 to 25 points in the Krio comparison are unlikely to be distinguishable from zero. Results should be read as a pilot.

## 7. Quality control

- Review gate with reviewer and date recorded in the data.
- Automated tests for parsing, option mapping, statistics, validation and the command line.
- Dataset SHA-256 and git commit recorded in every run's metadata.
- Mock runs write to `.dryrun/` and are labelled in any report.
- Canary string in the data files.

## 8. Reporting commitments

- Every completed run is published, including unfavourable results.
- The report states the run date, model strings, dataset hash and item approval status.
- If an item is found to be wrong after the first real run, the item bank is versioned, the change is logged below and the models are re-run on the corrected bank. Earlier results remain in the repository.

## 9. Ethics

No human participants and no patient data. The study evaluates software on published guidance. Outputs must not be used for clinical decisions.

## 10. Deviations log

| Date | Change | Reason |
|---|---|---|
| | | |
