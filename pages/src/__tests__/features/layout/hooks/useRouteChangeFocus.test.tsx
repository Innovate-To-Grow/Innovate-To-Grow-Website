import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Link, MemoryRouter, Navigate, Outlet, Route, Routes, useNavigate} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {useRouteChangeFocus} from '@/features/layout/hooks/useRouteChangeFocus';

afterEach(() => {
  cleanup();
});

/** The shell's content column, with a search box outside the routed page (it stays mounted). */
function Shell() {
  const ref = useRef<HTMLDivElement>(null);
  useRouteChangeFocus(ref);
  return (
    <>
      <input aria-label="Search the site" />
      <div ref={ref}>
        <Outlet />
      </div>
    </>
  );
}

const ListPage = () => {
  const navigate = useNavigate();
  return (
    <>
      <h1>Current Projects</h1>
      <Link to="/projects/abc">Solar drone</Link>
      <Link to="/current-projects?page=2">Next</Link>
      <Link to="/current-projects#results">Results</Link>
      <Link to="/profile">Profile</Link>
      <button type="button" onClick={() => void navigate('/projects/abc')}>
        Open from code
      </button>
    </>
  );
};

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

/** A page that renders its h1 only once its data has arrived. */
const LoadingDetailPage = () => {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setLoaded(true), 10);
    return () => window.clearTimeout(timer);
  }, []);
  return loaded ? <h1>Solar drone</h1> : <p>Loading project</p>;
};

/** A sign-in form: once the server answers, it replaces itself with the account page. */
const LoginPage = () => {
  const navigate = useNavigate();
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void Promise.resolve().then(() => navigate('/account', {replace: true}));
      }}
    >
      <h1>Sign in</h1>
      <button type="submit">Sign in</button>
    </form>
  );
};

const renderRoutes = (initialPath = '/current-projects', detail: ReactNode = <DetailPage />) =>
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/current-projects" element={<ListPage />} />
          <Route path="/projects-teams" element={<Navigate to="/current-projects" replace />} />
          <Route path="/profile" element={<Navigate to="/account" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/account" element={<h1>Account Dashboard</h1>} />
          <Route path="/projects/:id" element={detail} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

const clickLink = (name: string) => {
  act(() => {
    fireEvent.click(screen.getByRole('link', {name}));
  });
};

describe('useRouteChangeFocus', () => {
  it("moves focus to the new page's heading, but leaves the first page alone", () => {
    renderRoutes();
    expect(document.body).toHaveFocus();

    clickLink('Solar drone');

    const heading = screen.getByRole('heading', {level: 1, name: 'Solar drone'});
    expect(heading).toHaveFocus();
    expect(heading).toHaveAttribute('tabindex', '-1');
  });

  it('moves focus on back/forward too', () => {
    renderRoutes();
    clickLink('Solar drone');

    act(() => {
      fireEvent.click(screen.getByRole('button', {name: 'Browser back'}));
    });

    expect(screen.getByRole('heading', {level: 1, name: 'Current Projects'})).toHaveFocus();
  });

  it('waits for a page that renders its heading after its data arrives', async () => {
    renderRoutes('/current-projects', <LoadingDetailPage />);

    clickLink('Solar drone');

    expect(await screen.findByRole('heading', {level: 1, name: 'Solar drone'})).toHaveFocus();
  });

  it('does not move focus on a change within the page (query string or fragment)', () => {
    renderRoutes();
    expect(document.body).toHaveFocus(); // idle: nothing would stop a move but the same-page rule

    clickLink('Next');
    clickLink('Results');

    expect(screen.getByRole('heading', {level: 1, name: 'Current Projects'})).not.toHaveFocus();
    expect(document.body).toHaveFocus();
  });

  it('leaves focus the visitor has placed outside the page', () => {
    renderRoutes();
    const search = screen.getByRole('textbox', {name: 'Search the site'});
    search.focus();

    act(() => {
      fireEvent.click(screen.getByRole('button', {name: 'Open from code'}));
    });

    expect(screen.getByRole('heading', {level: 1, name: 'Solar drone'})).toBeInTheDocument();
    expect(search).toHaveFocus();
  });

  it('leaves the page the document loaded with alone when it redirects before the visitor moves', () => {
    renderRoutes('/projects-teams');

    const heading = screen.getByRole('heading', {level: 1, name: 'Current Projects'});
    expect(heading).not.toHaveFocus();
    expect(document.body).toHaveFocus();

    clickLink('Solar drone');
    expect(screen.getByRole('heading', {level: 1, name: 'Solar drone'})).toHaveFocus();
  });

  it("moves focus when the visitor's own step on the first page replaces it (a sign-in form)", async () => {
    renderRoutes('/login');
    const submit = screen.getByRole('button', {name: 'Sign in'});
    submit.focus();

    // A screen reader's activation: a click alone, with no pointer or key events before it.
    fireEvent.click(submit);

    await waitFor(() => expect(screen.getByRole('heading', {level: 1, name: 'Account Dashboard'})).toHaveFocus());
  });

  it('moves focus to where a link redirects to', () => {
    renderRoutes();

    clickLink('Profile');

    expect(screen.getByRole('heading', {level: 1, name: 'Account Dashboard'})).toHaveFocus();
  });
});
