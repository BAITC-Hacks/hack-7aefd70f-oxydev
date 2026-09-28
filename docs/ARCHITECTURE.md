# Architecture

## System context

Qadam is a responsive React application served by a FastAPI backend. One image
contains the compiled frontend, API, reproducible model training code and
offline extraction fallback.

```text
Applicant browser ─┐
                   ├─ HTTPS / FastAPI ─ SQLite pilot store
Reviewer browser ──┘                 ├─ local media directory
                                     ├─ deterministic classifier
                                     └─ optional LLM extraction provider
```

## Request flow

1. An applicant submits a story and scenario response after explicit consent.
2. The API assigns a random `QDM-…` reference and persists the submission.
3. Uploaded audio/video is stored as a separate binary object (30 MB maximum).
4. A reviewer opens the original evidence and selects a review route.
5. The decision, reason, evidence quote and timecode are appended to history.
6. Russian text can additionally enter the experimental leadership pipeline:
   extraction → quote verification → feature vector → calibrated classifier →
   explanation and abstention policy.

## Trust boundaries

- Cloud extraction is optional; the application degrades to a local heuristic.
- User text is never written to the extraction cache.
- The scoring model does not consume school, region, income, gender or polish.
- Audio/video is presented to a human; face, voice and emotion are not scored.
- The model offers decision support and cannot reject an applicant.

## Persistence

Development and demo environments use SQLite plus a local media directory.
Docker stores these under the `qadam-demo` volume. Production migration should
replace these with PostgreSQL, protected object storage and institutional IAM
without changing the public API contract.
