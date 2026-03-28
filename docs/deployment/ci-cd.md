# CI and Delivery Pipeline

## CI stages

- Ruff lint and format checks for backend code
- ESLint and TypeScript checks for frontend code
- Repository structure validation
- Django test suite and configuration checks
- Backend Docker build validation
- PostgreSQL migration validation
- Frontend production build

## Deployment flows

- `deploy-backend.yml` builds and pushes the ECS image, renders the task definition, deploys, and smoke-checks health.
- `deploy-frontend.yml` builds the frontend bundle and uploads it to Amplify.

## Notes

- CI remains the gate before either deployment workflow runs.
- Path assumptions in workflows must stay aligned with the repository structure.
