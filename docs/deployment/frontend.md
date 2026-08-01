# Frontend Deployment

The frontend is built with Vite and deployed to AWS Amplify, which serves it as a static site via S3 and CloudFront CDN.

## Build process

```bash
cd pages
npm ci
npm run build   # Runs: tsc -b && vite build
```

This produces a `pages/dist/` directory containing:
- `index.html` — Single HTML shell with three React mount points
- Hashed JS bundles, including lazy feature/export chunks
- CSS assets
- Static assets (images, fonts)
- Local vendor assets copied from `src/apps/core/static/vendor/` into `dist/static/vendor/`

### Code splitting

Configured in `pages/vite.config.ts`:

| Chunk | Contents |
|-------|----------|
| `react-vendor` | `react`, `react-dom` |
| `router` | `react-router` |
| Spreadsheet/PDF export chunks | Dynamically imported export libraries |
| Main bundle | Application code (lazy-loaded page components) |

All page components are lazy-loaded via `React.lazy()`, reducing the initial bundle size.

### Build-time environment

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Backend API URL (baked into the build) |

This must be set before building. CI builds separate production and demo
artifacts once with their reviewed target URLs; deploy consumes those exact
artifacts.

## Deployment flow

Called by the `deploy-production.yml` workflow after its unified approval (or
by the separately approved break-glass workflow):

1. **Select**: Resolve the successful `main` CI run and immutable full SHA
2. **Download**: Fetch the exact `frontend-dist-prod` or
   `frontend-dist-demo` artifact from that CI run
3. **Policy**: Render and validate the Amplify CSP configuration, including
   the configured CMS iframe origins
4. **Package/upload**: Zip the artifact and upload through the Amplify API
5. **Deploy/smoke**: Wait for Amplify and verify content type plus semantic
   application markers

### Trigger conditions

- Automatically selected by `Deploy Production` after successful CI completion
  on `main`
- Normal production workflows have no manual trigger
- Emergency rollback/redeploy uses the separately protected break-glass
  workflow with a main-reachable full SHA and mandatory reason

## Amplify configuration

AWS Amplify serves the static site with:
- S3 backend for file storage
- CloudFront CDN for global distribution
- SPA routing: all paths resolve to `index.html` (client-side routing)
- A report-only or enforcing CSP generated from the exact required script
  origins and configured CMS iframe hosts

The SPA routing configuration is critical — without it, direct navigation to frontend routes (e.g., `/about`) would return 404 from the CDN.

## Relationship to backend

In production, the frontend and backend are separate deployments:
- Frontend: Amplify CDN (static files)
- Backend: ECS Fargate (Django API)

The frontend makes API calls to the backend URL configured at build time (`VITE_API_BASE_URL`). CORS headers on the backend must allow the Amplify domain.

This is different from local development, where Vite proxies API calls to Django on the same origin.

## Related pages

- [Backend Deployment](backend.md) — ECS Fargate deployment
- [CI/CD](ci-cd.md) — Build pipelines
- [Architecture: Frontend](../architecture/frontend.md) — React architecture and routing
- [Environments](environments.md) — Environment configuration
- [Production Handoff Runbook](../operations/handoff-runbook.md) — CSP promotion and rollback
