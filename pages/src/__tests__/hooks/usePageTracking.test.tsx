import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {Container} from '@/features/layout/components/Container/Container';
import {usePageTracking} from '@/hooks/usePageTracking';
import {trackPageView} from '@/lib/analytics';

vi.mock('@/lib/analytics', () => ({
  trackPageView: vi.fn(),
}));

const TrackingProbe = () => {
  usePageTracking();
  return <div>Tracked</div>;
};

describe('page tracking', () => {
  beforeEach(() => {
    vi.mocked(trackPageView).mockReset();
  });

  it('tracks the current route once per rendered path', () => {
    Object.defineProperty(document, 'referrer', {
      configurable: true,
      value: 'https://referrer.example/page',
    });

    const {rerender} = render(
      <MemoryRouter initialEntries={['/projects']}>
        <TrackingProbe />
      </MemoryRouter>,
    );

    expect(trackPageView).toHaveBeenCalledWith({
      path: '/projects',
      referrer: 'https://referrer.example/page',
    });

    rerender(
      <MemoryRouter initialEntries={['/projects']}>
        <TrackingProbe />
      </MemoryRouter>,
    );

    expect(trackPageView).toHaveBeenCalledTimes(1);
  });

  it('renders the layout container outlet while installing page tracking', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<Container />}>
            <Route path="/" element={<div>Home outlet</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Home outlet')).toBeInTheDocument();
    expect(trackPageView).toHaveBeenCalledWith(expect.objectContaining({path: '/'}));
  });
});
