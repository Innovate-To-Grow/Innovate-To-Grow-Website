# Platform and Operations

## Infrastructure

- Backend deploys to AWS ECS using the Docker image built from `src/`.
- Frontend deploys to AWS Amplify from the Vite `dist/` bundle.
- Production cache uses Redis and production storage uses S3-compatible object storage.

## Integrations

- Google Sheets powers event, schedule, and project display flows.
- Gmail API and AWS SES are both supported for outbound email.
- RSS feeds populate the news system.

## Observability and safety

- Health endpoints are used by the SPA, middleware, and deployment smoke tests.
- CI validates formatting, linting, builds, tests, and migration state.
- Repository structure checks now run in CI to enforce file-length and directory-size limits.
