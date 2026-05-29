"""
Composable settings fragments.

Organized into subpackages by concern:

  framework/      – Core Django plumbing (paths, env vars, apps, middleware).
  integrations/   – Third-party package config (DRF, JWT, Unfold, CKEditor).
  production.py   – Production-only overlay (security, S3, logging, caching).

Assembled by ``base.py``; environment entrypoints (dev/prod/ci) import from
base and apply their own overrides.
"""
