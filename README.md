# Qadam AI

Evidence-first admissions assistant for inVision U. Qadam gives applicants a
short multilingual way to demonstrate how they act, then helps reviewers
inspect the original evidence, ask consistent follow-up questions and record a
human decision.

**Live demo:** https://oxydev.govtech-kz.com

## Product

### Applicant journey

- English, Kazakh and Russian interface;
- text, voice recording, video recording or an existing HTTPS video link;
- one behavioural story and one short team scenario;
- explicit pilot consent and anonymous `QDM-…` reference;
- responsive mobile-first experience.

### Reviewer workspace

- persistent review queue;
- original response, recording and scenario reasoning;
- evidence quote and optional media timecode;
- `manual review`, `priority interview` and `standard interview` routes;
- append-only review history;
- explainable experimental analysis for the published leadership example;
- nine-block Qadam Evidence Framework with clear validation status.

Qadam never issues an automatic rejection. English/Kazakh responses and media
remain human-reviewed until separate language and modality validation exists.

## Quick start

### Docker

```bash
docker compose up --build
```

Open http://127.0.0.1:8000. To use another host port:

```powershell
$env:QADAM_PORT = "8765"
docker compose up --build
```

### Native development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m eval.train
python -m uvicorn qadam.api.main:app --reload --port 8000
```

In a second terminal:

```bash
cd web
npm ci
npm run dev
```

The core works without a cloud AI key. If configured, extraction tries Groq,
then Anthropic, and falls back to the local deterministic extractor.

## Configuration

Copy `.env.example` to `.env`. Never commit `.env` or credentials.

| Variable | Purpose |
|---|---|
| `QADAM_PORT` | Docker host port; default `8000` |
| `QADAM_DEMO_PASSWORD` | Optional Basic Auth for a closed demo |
| `GROQ_API_KEY` | Optional cloud extraction provider |
| `ANTHROPIC_API_KEY` | Optional fallback extraction provider |
| `QADAM_PILOT_DB` | Optional SQLite path |
| `QADAM_PILOT_MEDIA` | Optional local media directory |

## Verification

```bash
python -m unittest discover -s tests -q

cd web
npm ci
npm run build
npm run test:e2e
```

Against a running deployment:

```powershell
$env:QADAM_BASE_URL = "https://oxydev.govtech-kz.com"
python scripts/demo_smoke.py
```

Current automated coverage: 11 API/unit tests and 7 end-to-end browser
scenarios covering the applicant journey, media, mobile layout, human review
and methodology labelling.

## Repository layout

```text
qadam/api/       FastAPI endpoints and local pilot stores
qadam/core/      extraction, features, model, explanation and fairness checks
qadam/data/      rubrics, QEF configuration and reproducible synthetic corpus
web/             React + TypeScript interface and Playwright scenarios
eval/            training, baselines and evaluation artefacts
tests/           backend workflow and privacy tests
scripts/         deployment smoke checks
docs/            maintained product and engineering documentation
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Evidence framework](docs/METHODOLOGY.md)
- [Security and privacy](docs/SECURITY.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Evaluation](docs/EVALUATION.md)
- [Two-minute demo](docs/DEMO.md)

## Status

Qadam is a complete demonstrator and controlled-pilot foundation. The full
nine-block framework is a versioned Qadam proposal, not an approved inVision U
admissions test. Production use requires expert content review, language-level
validation, institutional access control, retention policy and legal approval.
