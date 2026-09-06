import {cleanup, render, screen} from '@testing-library/react';
import type {ReactNode} from 'react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {Container} from '@/features/layout/components/Container/Container';

const usePageTracking = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/usePageTracking', () => ({
  usePageTracking,
}));

afterEach(() => {
  cleanup();
});

const renderContainer = (child: ReactNode) =>
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<Container />}>
          <Route path="/" element={child} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

describe('Container', () => {
  it('renders the outlet inside the layout container and tracks the page', () => {
    renderContainer(<div>Page Content</div>);

    expect(usePageTracking).toHaveBeenCalledOnce();
    expect(screen.getByText('Page Content')).toBeInTheDocument();
    expect(document.querySelector('.app-layout.container')).not.toBeNull();
  });

  it('shows the loading fallback while the outlet suspends', () => {
    const Suspend = () => {
      throw new Promise<void>(() => {});
    };

    renderContainer(<Suspend />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });
});
