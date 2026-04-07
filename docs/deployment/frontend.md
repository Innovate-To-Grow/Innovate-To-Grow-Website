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
- Hashed JS bundles (main app, react-vendor chunk, router chunk)
- CSS assets
- Static assets (images, fonts)

### Code splitting

Configured in `pages/vite.config.ts`:

| Chunk | Contents |
|-------|----------|
| `react-vendor` | `react`, `react-dom` |
| `router` | `react-router`, `react-router-dom` |
| Main bundle | Application code (lazy-loaded page components) |

All page components are lazy-loaded via `React.lazy()`, reducing the initial bundle size.

### Build-time environment

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Backend API URL (baked into the build) |

This must be set before building. In CI/CD, it's configured as a GitHub Actions secret.

## Deployment flow

Triggered by the `deploy-frontend.yml` GitHub Actions workflow:

1. **Build**: `npm run build` produces the `dist/` directory
2. **Package**: `dist/` is zipped into a deployment artifact
3. **Upload**: Artifact uploaded to S3 via a pre-signed URL
4. **Deploy**: AWS Amplify API triggers a deployment from the uploaded artifact

### Trigger conditions

- After successful CI completion (main branch)
- Manual workflow dispatch

## Amplify configuration

AWS Amplify serves the static site with:
- S3 backend for file storage
- CloudFront CDN for global distribution
- SPA routing: all paths resolve to `index.html` (client-side routing)

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
