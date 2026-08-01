# Architecture

Technical architecture of the Innovate To Grow platform — a Django REST Framework backend with a React/TypeScript frontend, deployed on AWS ECS (backend) and AWS Amplify (frontend).

## In this section

- [Repository Structure](repository-structure.md) — Top-level layout, directory conventions, and configuration files
- [Backend](backend.md) — Django apps, base models, settings, middleware, and auth system
- [Frontend](frontend.md) — React roots, router, features, shared modules, and styling
- [Request Flow](request-flow.md) — How requests move from browser through Vite/CDN to Django and back
- [Integrations](integrations.md) — External services: Google Sheets, AWS SES/End User Messaging/Bedrock, S3

## Who this is for

Engineers who need to understand how the system is organized before making changes. Start here if you are new to the codebase.

## Key architectural decisions

| Decision | Rationale |
|----------|-----------|
| Three independent React roots | Menu and footer update without full-page navigation; auth syncs via custom events |
| UUID primary keys on all domain models | `ProjectControlModel` base class provides UUIDs, timestamps, and soft delete |
| Block-based CMS | `CMSPage` + ordered `CMSBlock` records with JSON schemas replace the older GrapesJS system |
| Service layer pattern | Business logic lives in `services/` modules, not in views or serializers |
| Modular Django settings | `base.py` assembles shared components; `local.py`, `test.py`, and `production.py` apply environment-specific overrides |
| Per-endpoint throttling | Throttle classes applied per-view, not globally (global setting breaks test suite) |
| Client-side RSA password encryption | Passwords are encrypted with Web Crypto API; active keys rotate daily and retired key IDs remain decryptable for a bounded two-day window |
| Server-authoritative auth bootstrap | Persisted tokens identify a local session generation, while `/authn/session/` supplies the current member/profile state |
| Durable one-time challenges | Email, SMS, verification-token, and impersonation credentials use locked or conditional state transitions so concurrent reuse fails |

## Related sections

- [API Reference](../api/index.md) — Endpoint details and serializer behavior
- [Deployment Guide](../deployment/index.md) — How the architecture maps to infrastructure
- [CMS & Admin Guide](../cms-admin/index.md) — Content management workflows
