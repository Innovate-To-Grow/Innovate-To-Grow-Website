import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
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
});
