# Method

The full protocol is in [../PROTOCOL.md](../PROTOCOL.md). This page summarises what the Workbench computes.

## Construct

Recall and application of public health knowledge relevant to Sierra Leone, assessed by single-best-answer multiple choice. Items are original, anchored to public guidance (for example WHO IDSR technical guidelines), and not copied from exams.

## Procedure

- Zero-shot. One fixed system instruction asks for the answer letter only. Temperature 0.
- Each item is asked under three seeded permutations of the option order (repetitions are configurable from 1 to 10).
- The reply is parsed strictly. A reply without a single valid letter counts as incorrect and is reported as unparsed.

## Metrics

| Metric | Definition | Reading |
| --- | --- | --- |
| Item accuracy | For each item, share of completed calls answered correctly (unparsed replies count as wrong; calls that failed with an error are excluded and counted separately); averaged over items | Headline measure |
| 95% interval | 10,000 bootstrap resamples of items, seed 20261119 | Reflects item sampling |
| Order consistency | For each item, share of parsed replies that choose the most common content option across permutations; averaged over items | Needs 2 or more repetitions. 1.0 means the same content every time |
| Most-chosen letter share | Largest share of any answer letter across calls | Near 25% suggests no position preference |
| EN-KRI gap | English accuracy minus Krio accuracy on the same items | Reported only with at least 15 paired items |
| Key audit | Items where at least 75% of at least 3 models pick the same non-key option | Prompts human review |

## Interpretation rules

- Accuracy is an activity-level output of a benchmark. It is not an outcome or impact measure of any health programme.
- Differences smaller than the interval width are not evidence of a difference between models.
- Domain results hold roughly six items each.
- Results from draft items are provisional.
- Contamination: items carry a canary string. Public items can enter future training data, so scores may inflate over time.
