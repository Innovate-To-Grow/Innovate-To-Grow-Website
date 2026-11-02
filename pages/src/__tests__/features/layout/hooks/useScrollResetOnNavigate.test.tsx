import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {Link, MemoryRouter, Navigate, Outlet, Route, Routes, useNavigate} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {useScrollResetOnNavigate} from '@/features/layout/hooks/useScrollResetOnNavigate';

beforeEach(() => {
  // jsdom has no scrolling.
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Shell() {
  useScrollResetOnNavigate();
  return <Outlet />;
}

const ListPage = () => (
  <>
    <h1>Current Projects</h1>
    <Link to="/projects/abc">Solar drone</Link>
    <Link to="/current-projects?page=2">Next</Link>
    <Link to="/current-projects#results">Results</Link>
    <Link to="/profile">Profile</Link>
  </>
);

const DetailPage = () => {
  const navigate = useNavigate();
  return (
    <>
      <h1>Solar drone</h1>
      <button type="button" onClick={() => void navigate(-1)}>
        Browser back
      </button>
    </>
  );
};

const renderRoutes = () =>
  render(
    <MemoryRouter initialEntries={['/current-projects']}>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/current-projects" element={<ListPage />} />
          <Route path="/profile" element={<Navigate to="/account" replace />} />
          <Route path="/account" element={<h1>Account Dashboard</h1>} />
          <Route path="/projects/:id" element={<DetailPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

const click = (role: 'link' | 'button', name: string) => {
  act(() => {
    fireEvent.click(screen.getByRole(role, {name}));
  });
};

describe('useScrollResetOnNavigate', () => {
  it('starts a page reached by a link at the top, and leaves back/forward to the browser', () => {
    const scrollTo = vi.mocked(window.scrollTo);
    renderRoutes();
    expect(scrollTo).not.toHaveBeenCalled();

    click('link', 'Solar drone');
    expect(scrollTo).toHaveBeenCalledOnce();
    expect(scrollTo).toHaveBeenCalledWith(0, 0);

    click('button', 'Browser back');
    expect(screen.getByRole('heading', {level: 1, name: 'Current Projects'})).toBeInTheDocument();
    expect(scrollTo).toHaveBeenCalledOnce();
  });

  it('starts a page reached through a redirect at the top', () => {
    const scrollTo = vi.mocked(window.scrollTo);
    renderRoutes();

    click('link', 'Profile');

    expect(screen.getByRole('heading', {level: 1, name: 'Account Dashboard'})).toBeInTheDocument();
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
  });

  it('does not scroll on a change within the page (query string or fragment)', () => {
    const scrollTo = vi.mocked(window.scrollTo);
    renderRoutes();

    click('link', 'Next');
    click('link', 'Results');

    expect(scrollTo).not.toHaveBeenCalled();
  });
});
