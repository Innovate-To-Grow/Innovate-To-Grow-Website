import type {ReactElement} from 'react';
import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter, Navigate, Route, Routes, useLocation} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

vi.mock('@/features/cms', () => ({
  CMSPageComponent: ({routeOverride}: {routeOverride?: string}) => (
    <div data-testid="cms-route">{routeOverride}</div>
  ),
}));

import {HomepageResolver} from '@/app/router/HomepageResolver';
import {LegacyLoginLinkRedirect} from '@/app/router/LegacyLoginLinkRedirect';

function LocationState() {
  const location = useLocation();
  return (
    <div data-testid="destination">
      {location.pathname}{location.search}{location.hash}
    </div>
  );
}

describe('router helpers', () => {
  afterEach(cleanup);
  it('resolves the homepage immediately without waiting for layout', () => {

    render(<HomepageResolver />);

    expect(screen.getByTestId('cms-route')).toHaveTextContent('/');
  });

  it.each(['/magic-login', '/ticket-login'])(
    'redirects %s to the canonical route while preserving non-secret URL state',
    (legacyPath) => {
      render(
        <MemoryRouter initialEntries={[`${legacyPath}?source=email#continue`]}>
          <Routes>
            <Route path={legacyPath} element={<LegacyLoginLinkRedirect />} />
            <Route path="/login-link" element={<LocationState />} />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('destination')).toHaveTextContent(
        '/login-link?source=email#continue',
      );
    },
  );

  it('redirects the retired /unsubscribe-login to /account and drops its token', async () => {
    const {createAppRouter} = await import('@/app/router');
    const rootRoute = createAppRouter().routes.find((route) => route.path === '/');
    const legacyRoute = rootRoute?.children?.find(
      (route) => 'path' in route && route.path === 'unsubscribe-login',
    ) as {element?: ReactElement} | undefined;

    // A bare redirect, not a page: nothing loads and no token is exchanged.
    expect(legacyRoute?.element?.type).toBe(Navigate);

    render(
      <MemoryRouter initialEntries={['/unsubscribe-login?token=expired#token=expired']}>
        <Routes>
          <Route path="/unsubscribe-login" element={legacyRoute?.element} />
          <Route path="/account" element={<LocationState />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('destination').textContent).toBe('/account');
  });
});
