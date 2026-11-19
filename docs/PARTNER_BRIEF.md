# Partner brief

## Purpose

AI tools are being offered to health systems in Sierra Leone with little evidence from local conditions. The Workbench gives a ministry, a development partner or an academic group a repeatable way to test candidate models before any deployment decision, and to keep the evidence in a form others can check.

## What it does today (version 0.1)

- Runs a fixed protocol of 48 original public health multiple-choice questions across eight domains: surveillance, Lassa fever, cholera, malaria, maternal and newborn health, child health, infection control, and health information.
- Tests a 20-item Krio subset against the same questions in English.
- Reports accuracy with 95% bootstrap intervals, order consistency, position bias, and an answer-key audit.
- Runs on a laptop, offline for review and, with a local model endpoint, offline for testing.
- Accepts a partner's own item bank in CSV, so the same machinery can test local protocols.
- Exports a standalone HTML report.

## What it does not do

- It does not show that a tool is safe or fit for clinical use. Multiple-choice knowledge is a narrow proxy.
- It does not test free-text advice, referral decisions, patient-facing safety, bias across populations, or workflow fit.
- The 48 items are approved by their author only. Independent review by a clinician or programme expert, and a second Krio reader, are still needed before results are treated as more than a pilot.

## Where it fits in a deployment decision

| Stage | Question | Covered here |
| --- | --- | --- |
| Screening | Does the model know basic public health content relevant to Sierra Leone? | Yes, in part |
| Language | Does performance drop in Krio? | Indicative only, small sample |
| Local fit | Does the model follow national protocols? | Only if the partner supplies a reviewed item bank |
| Safety and harm | Does it give dangerous advice? | No |
| Field pilot | Does it help health workers in practice? | No |

## Governance

Every item carries a review status. Results from unapproved items are labelled provisional on screen and in exports. Simulated runs are labelled simulated. The protocol, item bank, code and results are public in the repository, so an external reviewer can reproduce a run.

## Possible next steps with partners

1. A reviewed national item bank, built with programme staff, aligned to current national guidelines.
2. A second Krio reader and back-translation of the Krio subset.
3. Free-text scenario evaluation with clinician scoring, as a separate protocol.
4. A shared results register so ministries can compare candidate tools on the same footing.

These are proposals, not commitments.

Contact: Alhassan Mayei, alhassanmayei@gmail.com
