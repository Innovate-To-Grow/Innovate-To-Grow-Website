import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import type {ReactNode} from 'react';
import {Link, MemoryRouter, Navigate, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {Menu, MenuItem} from '@/features/layout/api';
import {Container} from '@/features/layout/components/Container/Container';
import {LayoutContext, type LayoutContextValue} from '@/features/layout/components/LayoutProvider/context';
import {ROUTE_CHANGE_EVENT} from '@/features/layout/hooks/useCurrentPathname';

const usePageTracking = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/usePageTracking', () => ({
  usePageTracking,
}));

beforeEach(() => {
  // jsdom has no scrolling; the shell scrolls a page reached by a link to the top.
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const item = (title: string, url: string, children: MenuItem[] = []): MenuItem => ({
  title,
  url,
  type: 'app',
  open_in_new_tab: false,
  children,
});

const menu: Menu = {
  id: 'menu-main',
  name: 'main',
  display_name: 'Main',
  description: null,
  items: [
    item('Home', '/'),
    item('Projects', '/projects', [item('Current Projects', '/current-projects'), item('Past Projects', '/past-projects')]),
    item('News', '/news'),
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const layoutValue: LayoutContextValue = {state: 'ready', menus: [menu], footer: null, error: null};

const renderContainer = (child: ReactNode, path = '/', value?: LayoutContextValue) => {
  const tree = (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Container />}>
          <Route path="*" element={child} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
  return render(value ? <LayoutContext.Provider value={value}>{tree}</LayoutContext.Provider> : tree);
};

describe('Container', () => {
  it('renders the outlet inside the layout container and tracks the page', () => {
    renderContainer(<div>Page Content</div>);

    expect(usePageTracking).toHaveBeenCalled();
    expect(screen.getByText('Page Content')).toBeInTheDocument();
    expect(document.querySelector('.app-layout.container .app-layout-main')).toHaveTextContent('Page Content');
  });

  it('shows the loading fallback while the outlet suspends', () => {
    const Suspend = () => {
      throw new Promise<void>(() => {});
    };

    renderContainer(<Suspend />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders no section sidebar or section select, even on a page in a menu section', () => {
    renderContainer(<h1>Current Projects</h1>, '/current-projects', layoutValue);

    const layout = document.querySelector('.app-layout') as HTMLElement;
    expect(layout.children).toHaveLength(1);
    expect(layout.firstElementChild).toHaveClass('app-layout-main');
    expect(screen.queryByRole('navigation')).toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('announces route changes for the header root outside the router', () => {
    const seen: string[] = [];
    const listener = (event: Event) => seen.push((event as CustomEvent<{pathname: string}>).detail.pathname);
    window.addEventListener(ROUTE_CHANGE_EVENT, listener);
    try {
      renderContainer(<Link to="/past-projects">Go</Link>, '/current-projects', layoutValue);
      expect(seen).toEqual(['/current-projects']);

      act(() => {
        fireEvent.click(screen.getByRole('link', {name: 'Go'}));
      });
      expect(seen).toEqual(['/current-projects', '/past-projects']);
    } finally {
      window.removeEventListener(ROUTE_CHANGE_EVENT, listener);
    }
  });

  // The focus and scroll rules themselves: __tests__/features/layout/hooks/.
  describe('after a client-side route change', () => {
    const ListPage = () => (
      <>
        <h1>Current Projects</h1>
        <Link to="/projects/abc">Solar drone</Link>
      </>
    );

    const renderRoutes = (initialPath: string) =>
      render(
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route element={<Container />}>
              <Route path="/current-projects" element={<ListPage />} />
              <Route path="/projects-teams" element={<Navigate to="/current-projects" replace />} />
              <Route path="/projects/:id" element={<h1>Solar drone</h1>} />
            </Route>
          </Routes>
        </MemoryRouter>,
      );

    it("moves focus to the new page's heading and starts it at the top", () => {
      const scrollTo = vi.mocked(window.scrollTo);
      renderRoutes('/current-projects');
      expect(document.body).toHaveFocus();

      act(() => {
        fireEvent.click(screen.getByRole('link', {name: 'Solar drone'}));
      });

      expect(screen.getByRole('heading', {level: 1, name: 'Solar drone'})).toHaveFocus();
      expect(scrollTo).toHaveBeenCalledWith(0, 0);
    });

    it('leaves focus alone when the loaded page redirects (a cold load of /projects-teams)', () => {
      renderRoutes('/projects-teams');

      expect(screen.getByRole('heading', {level: 1, name: 'Current Projects'})).not.toHaveFocus();
      expect(document.body).toHaveFocus();
    });
  });
});
