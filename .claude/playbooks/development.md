# Development Workflow

## Full-stack local loop

1. Start Django from `src/`.
2. Start Vite from `pages/`.
3. Exercise the affected flows in the browser.
4. Run lint, type, build, and targeted tests before finishing.

## Migration workflow

- Generate migrations with `python manage.py makemigrations`.
- Apply them with `python manage.py migrate`.
- Keep migration validation green in CI.

## Source hygiene

- Avoid mixing generated files with source edits.
- Keep commits scoped by subsystem when possible.
- Preserve user changes already present in the worktree unless you intentionally build on top of them.
