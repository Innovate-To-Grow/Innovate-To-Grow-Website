# CMS & Admin Guide

Content management, Django admin operations, and member/mail tooling for the Innovate To Grow platform.

## In this section

- [Content Management](content-management.md) — CMS pages, blocks, news, and the content editing workflow
- [Django Admin](django-admin.md) — Admin theme, customizations, and navigation
- [Member & Mail Tools](member-and-mail-tools.md) — Member management, email campaigns, and contact tools
- [Operations](operations.md) — Maintenance mode, data management, and operational tasks

## Who this is for

Site administrators managing content, engineers customizing admin behavior, and operators handling maintenance tasks.

## Overview

The platform uses two content systems:

1. **Block-based CMS** — Dynamic pages composed of ordered content blocks (`CMSPage` + `CMSBlock`). Pages are addressable by route and rendered on the frontend by block type.
2. **News articles** — Synced from external RSS feeds via the `sync_news` management command, displayed on the `/news` frontend route.

All content management happens through the Django admin interface, which uses the Unfold theme with a custom color palette and organized sidebar navigation.

## Admin access

- **URL**: `/admin/` (custom login at `/admin/login/`)
- **Login**: Uses the custom `AdminLoginView` from the `authn` app
- **Superuser creation**: `python manage.py createsuperuser` — prompts for email, not username
- **Admin invitations**: Staff can send invitations via `AdminInvitation` model

## Related sections

- [Architecture: Backend](../architecture/backend.md) — App structure and base models
- [API: CMS & News](../api/cms-and-news.md) — CMS and news API endpoints
- [Deployment: Local Development](../deployment/local-development.md) — Running the admin locally
