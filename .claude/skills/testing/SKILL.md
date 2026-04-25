---
name: testing
description: Use this skill when writing or running backend Django tests or frontend Vitest tests.
---
# Testing Strategy

## Backend Tests

### Running

```bash
cd src && python manage.py test --settings=core.settings.dev                      # all tests
cd src && python manage.py test event.tests.test_current_projects --settings=core.settings.dev  # one module
cd src && python manage.py test event.tests.test_current_projects.CurrentProjectsAPIViewTest.test_returns_newest_published_semester --settings=core.settings.dev  # one test
```

### File Structure

Tests mirror the app structure under `src/<app>/tests/`:
```
tests/
  __init__.py
  helpers.py           # Shared test utilities
  admin/               # Admin interface tests
  api/                 # API endpoint tests
  models/              # Model tests
  services/            # Service layer tests
```

### Canonical Pattern

```python
# src/<app>/tests/<test_name>.py
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

class MyAPIViewTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_returns_200(self):
        response = self.client.get("/myapp/endpoint/")
        self.assertEqual(response.status_code, 200)

    def test_response_shape(self):
        response = self.client.get("/myapp/endpoint/")
        self.assertIn("id", response.data)
        self.assertIsInstance(response.data["items"], list)
```

See `src/event/tests/test_current_projects.py` for a full example.

### Key Patterns

- Always call `cache.clear()` in `setUp` to avoid cross-test pollution.
- Use `APIClient` from `rest_framework.test` (not Django's default client).
- Test URLs use the full path without `/api` prefix: `/authn/login/`, `/event/projects/`.
- Use `response.data` (parsed dict) to check content, not `response.json()`.
- Create test users: `Member.objects.create_user(email="test@example.com", password="StrongPass123!", is_active=True)`.
- JWT auth: `RefreshToken.for_user(member)` → `self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")`.
- Mock external deps with `@patch()` (Twilio, Google APIs, email sending).

### What to Test

- HTTP status codes for success and error paths.
- Response body structure and field values.
- Permission enforcement (authenticated vs. unauthenticated).
- Validation error responses (400 with field-level errors).
- Cache behavior (populated after first request, served on second).

## Frontend Tests

### Running

```bash
cd pages && npx vitest run          # single run
cd pages && npx vitest              # watch mode
cd pages && npx vitest run --reporter=verbose  # verbose (CI mode)
```

### Configuration

- Config: `pages/vitest.config.ts` — jsdom environment, setup file at `src/__tests__/setup.ts`.
- Test timeout: 30 seconds.
- Test file pattern: `src/**/*.test.{ts,tsx}`.

### Canonical Pattern

```typescript
// pages/src/pages/<PageName>/<PageName>.test.tsx
import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it, vi} from 'vitest';

vi.mock('../../shared/api/client');

describe('MyComponent', () => {
  it('renders heading', () => {
    render(
      <MemoryRouter>
        <MyComponent />
      </MemoryRouter>
    );
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });
});
```

### Key Patterns

- Wrap routed components in `<MemoryRouter>`.
- Mock at module level with `vi.mock()`.
- Mock auth: `vi.mock('../../components/Auth/AuthContext', () => ({ useAuth: () => ({...}) }))`.
- Use `vi.fn()` for function mocks, `vi.importActual()` when partially mocking.
- Co-locate tests: `pages/src/pages/<PageName>/<PageName>.test.tsx`.

## CI Pipeline

1. Backend: Ruff lint → Django tests (PostgreSQL) → Docker build → migration validation.
2. Frontend: ESLint → `tsc --noEmit` → Vitest → Vite build.
3. All checks must pass before merge.

## Do NOT

- Skip `cache.clear()` in backend test `setUp`.
- Use `response.json()` with DRF tests — use `response.data`.
- Hardcode integer IDs in test assertions — models use UUIDs.
- Forget `<MemoryRouter>` wrapper in frontend component tests.
- Mock entire modules when you only need one export — use `vi.importActual`.

## Key Files

- `src/event/tests/test_current_projects.py` — canonical backend API test
- `src/authn/tests/api/test_token_and_profile.py` — JWT-authenticated test
- `src/authn/tests/helpers.py` — shared test utilities
- `pages/src/__tests__/setup.ts` — Vitest setup
- `pages/vitest.config.ts` — Vitest configuration
- `.github/workflows/ci.yml` — CI pipeline
