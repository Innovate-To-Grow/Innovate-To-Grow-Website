import {render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {HomepageResolver} from '@/app/HomepageResolver';

const appMocks = vi.hoisted(() => ({
  layoutValue: {
    homepage_route: '/home',
    state: 'ready',
  },
}));

vi.mock('@/features/layout/components/LayoutProvider/context', () => ({
  useLayout: () => appMocks.layoutValue,
}));

vi.mock('@/features/cms', () => ({
  CMSPageComponent: ({routeOverride}: {routeOverride?: string}) => (
    <div data-testid="cms-page">{routeOverride}</div>
  ),
}));

describe('HomepageResolver', () => {
  beforeEach(() => {
    appMocks.layoutValue = {
      homepage_route: '/home',
      state: 'ready',
    };
  });

  it('renders nothing while layout data is loading', () => {
    appMocks.layoutValue = {
      homepage_route: '/home',
      state: 'loading',
    };

    const {container} = render(<HomepageResolver />);
    expect(container).toBeEmptyDOMElement();
  });

  it('passes the configured homepage route to the CMS page component', () => {
    render(<HomepageResolver />);

    expect(screen.getByTestId('cms-page')).toHaveTextContent('/home');
  });

  it('falls back to the root CMS route when no homepage route is configured', () => {
    appMocks.layoutValue = {
      homepage_route: '',
      state: 'ready',
    };

    render(<HomepageResolver />);

    expect(screen.getByTestId('cms-page')).toHaveTextContent('/');
  });
});
