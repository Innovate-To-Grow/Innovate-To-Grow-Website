import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Link, RouterProvider, createMemoryRouter, useLocation, useNavigate} from 'react-router';

import {usePopOutNavigation} from '@/features/cms/components/embed/usePopOutNavigation';

/** A widget page with a link out of the embed, a search change inside it, and the blocked-tab fallback. */
const Widget = () => {
  const blocked = usePopOutNavigation();
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <p data-testid="location">{location.pathname + location.search}</p>
      <Link to="/projects/abc?tab=team#members">Project ABC</Link>
      <button type="button" onClick={() => navigate('?page=2')}>
        Next page
      </button>
      <button type="button" onClick={() => navigate('/projects/abc', {state: {saved: true}})}>
        Save
      </button>
      {blocked ? (
        <Link to={blocked.to} state={blocked.state}>
          Blocked: {blocked.to}
        </Link>
      ) : null}
    </>
  );
};

const ProjectPage = () => {
  const {state} = useLocation();
  return <h1>Project detail page{(state as {saved?: boolean} | null)?.saved ? ' (saved)' : ''}</h1>;
};

const renderWidget = () => {
  const router = createMemoryRouter(
    [
      {path: '/_embed/:embedSlug', element: <Widget />},
      {path: '/projects/:id', element: <ProjectPage />},
    ],
    {initialEntries: ['/_embed/current-projects-widget']},
  );
  render(<RouterProvider router={router} />);
  return router;
};

const setUserActivation = (value: {isActive: boolean} | undefined) =>
  Object.defineProperty(window.navigator, 'userActivation', {configurable: true, value});

// A real click, as the browser dispatches it (testing-library's events are untrusted).
const asTrustedClicks = () => vi.spyOn(window, 'event', 'get').mockReturnValue({isTrusted: true} as Event);

describe('usePopOutNavigation', () => {
  afterEach(() => {
    cleanup();
    setUserActivation(undefined);
    vi.restoreAllMocks();
  });

  it('opens a link to another page in a new tab and keeps the widget in the frame', () => {
    const tab = {opener: window} as unknown as Window;
    const open = vi.spyOn(window, 'open').mockReturnValue(tab);
    const router = renderWidget();

    fireEvent.click(screen.getByRole('link', {name: 'Project ABC'}));

    expect(open).toHaveBeenCalledWith(`${window.location.origin}/projects/abc?tab=team#members`, '_blank');
    expect(tab.opener).toBeNull();
    expect(router.state.location.pathname).toBe('/_embed/current-projects-widget');
    expect(screen.queryByRole('heading', {name: 'Project detail page'})).toBeNull();
    expect(screen.queryByRole('link', {name: /Blocked:/})).toBeNull();
  });

  it('keeps search changes inside the widget', () => {
    const open = vi.spyOn(window, 'open');
    renderWidget();

    fireEvent.click(screen.getByRole('button', {name: 'Next page'}));

    expect(screen.getByTestId('location')).toHaveTextContent('/_embed/current-projects-widget?page=2');
    expect(open).not.toHaveBeenCalled();
  });

  it('opens the page in the frame when a click cannot open a tab (sandboxed without allow-popups)', () => {
    asTrustedClicks();
    vi.spyOn(window, 'open').mockReturnValue(null);
    const router = renderWidget();

    fireEvent.click(screen.getByRole('link', {name: 'Project ABC'}));

    expect(router.state.location.pathname).toBe('/projects/abc');
    expect(screen.getByRole('heading', {name: 'Project detail page'})).toBeInTheDocument();
  });

  it('opens the page in the frame when window.open throws, as Firefox does in such a sandbox', () => {
    asTrustedClicks();
    vi.spyOn(window, 'open').mockImplementation(() => {
      throw new DOMException('A parameter or an operation is not supported', 'InvalidAccessError');
    });
    const router = renderWidget();

    fireEvent.click(screen.getByRole('link', {name: 'Project ABC'}));

    expect(router.state.location.pathname).toBe('/projects/abc');
    expect(screen.getByRole('heading', {name: 'Project detail page'})).toBeInTheDocument();
  });

  it('hands a navigation without a click back, and its link opens the tab', () => {
    setUserActivation({isActive: false});
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    const router = renderWidget();

    fireEvent.click(screen.getByRole('button', {name: 'Save'}));

    expect(open).not.toHaveBeenCalled();
    expect(router.state.location.pathname).toBe('/_embed/current-projects-widget');
    const fallback = screen.getByRole('link', {name: 'Blocked: /projects/abc'});

    setUserActivation({isActive: true});
    fireEvent.click(fallback);

    expect(open).toHaveBeenCalledWith(`${window.location.origin}/projects/abc`, '_blank');
    expect(router.state.location.pathname).toBe('/_embed/current-projects-widget');
    expect(screen.queryByRole('link', {name: /Blocked:/})).toBeNull();
  });

  it('hands back a tab refused after the click (as Safari refuses one once a save request returns)', () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const router = renderWidget();

    fireEvent.click(screen.getByRole('button', {name: 'Save'}));

    expect(router.state.location.pathname).toBe('/_embed/current-projects-widget');
    expect(screen.getByRole('link', {name: 'Blocked: /projects/abc'})).toBeInTheDocument();
  });

  it("keeps the navigation's state when its link has to open the page in the frame", () => {
    setUserActivation({isActive: false});
    vi.spyOn(window, 'open').mockReturnValue(null);
    renderWidget();

    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    setUserActivation({isActive: true});
    asTrustedClicks();
    fireEvent.click(screen.getByRole('link', {name: 'Blocked: /projects/abc'}));

    expect(screen.getByRole('heading', {name: 'Project detail page (saved)'})).toBeInTheDocument();
  });
});
