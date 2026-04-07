# Architecture

Technical architecture of the Innovate To Grow platform — a Django REST Framework backend with a React/TypeScript frontend, deployed on AWS ECS (backend) and AWS Amplify (frontend).

## In this section

- [Repository Structure](repository-structure.md) — Top-level layout, directory conventions, and configuration files
- [Backend](backend.md) — Django apps, base models, settings, middleware, and auth system
- [Frontend](frontend.md) — React roots, router, features, shared modules, and styling
- [Request Flow](request-flow.md) — How requests move from browser through Vite/CDN to Django and back
- [Integrations](integrations.md) — External services: Google Sheets, AWS SES, Twilio, S3

## Who this is for

Engineers who need to understand how the system is organized before making changes. Start here if you are new to the codebase.

## Key architectural decisions

| Decision | Rationale |
|----------|-----------|
| Three independent React roots | Menu and footer update without full-page navigation; auth syncs via custom events |
| UUID primary keys on all domain models | `ProjectControlModel` base class provides UUIDs, timestamps, and soft delete |
| Block-based CMS | `CMSPage` + ordered `CMSBlock` records with JSON schemas replace the older GrapesJS system |
| Service layer pattern | Business logic lives in `services/` modules, not in views or serializers |
| Modular Django settings | `base.py` wildcard-imports from `components/`; `dev.py`, `ci.py`, `prod.py` extend it |
| Per-endpoint throttling | Throttle classes applied per-view, not globally (global setting breaks test suite) |
| Client-side RSA password encryption | Passwords encrypted with Web Crypto API before transmission; key rotated on login |

## Related sections

- [API Reference](../api/index.md) — Endpoint details and serializer behavior
- [Deployment Guide](../deployment/index.md) — How the architecture maps to infrastructure
- [CMS & Admin Guide](../cms-admin/index.md) — Content management workflows
