# Qadam Evidence Framework

Version: `qef-0.1.0`

Status: Qadam proposal awaiting expert review; not an approved inVision U test.

## Principle

The unit of interpretation is evidence demonstrated in a specific response,
not a judgement about the applicant's personality. Every block uses the same
three evidence states:

1. **Insufficient evidence** — ask a follow-up; never treat this as low ability.
2. **Emerging** — a concrete example exists but part of the chain is missing.
3. **Consistently demonstrated** — action, reasoning, outcome, learning and
   transfer are connected by observable evidence.

ATOLA structures behavioural evidence: Action, Thinking, Outcome, Learnings
and Application.

## Blocks

| Block | Decision mode |
|---|---|
| University motivation | Human review |
| Field motivation | Human review |
| Leadership | Experimental model + human review |
| Teamwork | Human review |
| Values in action | Human only; unscored |
| Applied experience | Human review |
| Learning agility | Human review |
| Purpose-driven leadership | Human review |
| Growth through adversity | Optional, human only; unscored |

The executable definitions, prompts, probes and behavioural anchors live in
[`qadam/data/evidence_framework.py`](../qadam/data/evidence_framework.py) and
are exposed by `GET /methodology` with their version and status.

## Validation gates

1. Independent content review by two or more domain experts.
2. Cognitive walkthrough with target-age volunteers.
3. Blind double-rating of fictional boundary cases.
4. Agreement, calibration and counterfactual fairness reporting.
5. Prospective controlled pilot with consent and an appeal/review process.

Until these gates pass, QEF is used to structure evidence and interviews, not
to automate admission decisions.
