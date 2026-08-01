# Deployment Guide

How to run, build, and deploy the Innovate To Grow platform across local, CI, and production environments.

## In this section

- [Local Development](local-development.md) — Setting up and running the project locally
- [Environments](environments.md) — Configuration differences across dev, CI, and production
- [Backend Deployment](backend.md) — Docker, ECS Fargate, and Uvicorn
- [Frontend Deployment](frontend.md) — Vite build and AWS Amplify
- [CI/CD](ci-cd.md) — GitHub Actions pipelines
- [Production Deployment Configuration](production.md) — GitHub Environments,
  AWS identity, target variables, and protection rules
- [Production Handoff Runbook](../operations/handoff-runbook.md) — Worker,
  incident, reconciliation, rotation, rollback, and release procedures

## Who this is for

Engineers setting up a local development environment, deploying changes, or debugging environment-specific issues.

## Infrastructure overview

| Component | Local | CI | Production |
|-----------|-------|-----|------------|
| Backend | Django dev server (port 8000) | Docker build + PostgreSQL service | ECS Fargate (Uvicorn, port 8000) |
| Frontend | Vite dev server (port 5173) | npm build validation | AWS Amplify (S3 + CDN) |
| Database | SQLite | PostgreSQL 16 (GH Actions service) | PostgreSQL + SSL |
| Cache | LocMemCache | LocMemCache | Redis (required for enabled assistant budgeting) |
| File storage | Local filesystem | Local filesystem | S3 via django-storages |
| Email | Console (stdout) | Console (stdout) | AWS SES |
| Durable jobs | In-process fallback by default | PostgreSQL outbox tests | PostgreSQL outbox + ECS worker |
| Load balancer | None | None | ALB with health probes |

## Quick start

```bash
# Backend
cd src
cp .env.example .env          # Edit with your values
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install --require-hashes -r requirements/local.lock.txt
python manage.py migrate
python manage.py createsuperuser  # Prompts for email
python manage.py runserver

# Frontend (separate terminal)
cd pages
npm ci
npm run dev
```

Open `http://localhost:5173` — the Vite dev server proxies API calls to Django.

## Related sections

- [Architecture](../architecture/index.md) — System design and app structure
- [Google Sheets: Operations](../integrations/google-sheets/operations.md) — Integration setup
- [CMS & Admin: Operations](../cms-admin/operations.md) — Admin operational guidance
