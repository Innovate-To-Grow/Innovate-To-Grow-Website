# Repository Structure and Naming

## Top-level boundaries

- `src/`: Django backend and backend-side utilities.
- `pages/`: React frontend.
- `docs/`: human-facing project documentation.
- `aws/`: deployment templates and cloud-specific assets.
- `.claude/`: assistant guidance and local playbooks.
- `archive/`: historical or legacy assets that are not part of the active product.

## Placement rules

- New frontend domain logic belongs under `pages/src/features/<feature>/`.
- Shared frontend code belongs under `pages/src/shared/`.
- Backend domain logic stays inside its Django app and should prefer subpackages over oversized flat modules.
- Large config or content blobs belong in fixtures or reference files, not inside logic-heavy modules.

## Naming rules

- Prefer intent-revealing filenames such as `profile_update.py` over generic catch-all names.
- Avoid growing new `views.py`, `serializers.py`, `Auth.css`, or similarly broad files.
- Use `index.ts` and `__init__.py` only as export surfaces, not as implementation dumping grounds.

## Limits

- Active first-party text files should stay at or below 200 lines.
- A directory should not exceed 8 same-role source files after excluding `index.ts`, `__init__.py`, `README.md`, and manifest-only files.
- Historical migrations, lockfiles, generated assets, caches, and archived content are exempt from the active limits.
