# Deployment

## Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:${QADAM_PORT:-8000}/health
```

The compose project binds the service to `127.0.0.1`; expose it through an
HTTPS reverse proxy. Persistent model, cache and demo data use named volumes.

## Current demo

- URL: `https://oxydev.govtech-kz.com`
- reverse-proxy upstream: `127.0.0.1:8017`
- runtime: rootless Docker Compose on Ubuntu
- extraction backend: offline heuristic (no cloud secret required)

No server password, SSH credential or object-storage key belongs in this
repository.

## Health and smoke checks

```bash
curl -fsS https://oxydev.govtech-kz.com/health
QADAM_BASE_URL=https://oxydev.govtech-kz.com python scripts/demo_smoke.py
```

After deployment, verify the candidate journey, reviewer queue, media playback,
methodology page and cleanup of any test submission.
