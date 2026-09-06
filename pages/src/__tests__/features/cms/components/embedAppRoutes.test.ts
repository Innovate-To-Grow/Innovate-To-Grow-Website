import {cleanup, render, waitFor} from '@testing-library/react';
import {createElement, Suspense} from 'react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {resolveEmbedAppRoute} from '@/features/cms/components/embedAppRoutes';

describe('resolveEmbedAppRoute', () => {
  it('returns null for null, undefined, and empty strings', () => {
    expect(resolveEmbedAppRoute(null)).toBeNull();
    expect(resolveEmbedAppRoute(undefined)).toBeNull();
    expect(resolveEmbedAppRoute('')).toBeNull();
  });

  it('returns null for an unknown route', () => {
    expect(resolveEmbedAppRoute('/nonexistent')).toBeNull();
  });

  it('returns a lazy component for each known route', () => {
    const knownRoutes = [
      '/schedule',
      '/current-projects',
      '/presenting-teams',
      '/past-projects',
      '/acknowledgement',
      '/news',
      '/event-registration',
      '/subscribe',
    ];

    for (const route of knownRoutes) {
      expect(resolveEmbedAppRoute(route)).toBeTruthy();
    }
  });
});

describe('embed app route lazy components', () => {
  afterEach(() => {
    cleanup();
  });

  it('loads every registered app route component', async () => {
    const knownRoutes = [
      '/schedule',
      '/current-projects',
      '/presenting-teams',
      '/past-projects',
      '/acknowledgement',
      '/news',
      '/event-registration',
      '/subscribe',
    ];

    for (const route of knownRoutes) {
      const Component = resolveEmbedAppRoute(route);
      expect(Component).not.toBeNull();

      const {container} = render(
        createElement(
          MemoryRouter,
          {initialEntries: [route]},
          createElement(
            Suspense,
            {fallback: createElement('div', {'data-testid': 'suspense-fallback'}, 'loading')},
            createElement(Component!),
          ),
        ),
      );

      // Suspense swaps the fallback for the resolved page once the dynamic
      // import settles. Waiting for that swap covers the lazy `import().then`
      // bodies in the registry.
      await waitFor(() => {
        expect(container.querySelector('[data-testid="suspense-fallback"]')).toBeNull();
      });

      cleanup();
    }
  });
});
