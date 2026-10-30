import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Link, RouterProvider, createMemoryRouter, useLocation, useNavigate} from 'react-router';

import {usePopOutNavigation} from '@/features/cms/components/embed/usePopOutNavigation';

/** A widget page with a link out of the embed, a search change inside it, and the blocked-tab fallback. */
const Widget = () => {
  const {blockedUrl, clearBlockedUrl} = usePopOutNavigation();
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <p data-testid="location">{location.pathname + location.search}</p>
      <Link to="/projects/abc?tab=team#members">Project ABC</Link>
      <button type="button" onClick={() => navigate('?page=2')}>
        Next page
      </button>
      {blockedUrl ? (
        <button type="button" onClick={clearBlockedUrl}>
          Blocked: {blockedUrl}
        </button>
      ) : null}
    </>
  );
};

const renderWidget = () => {
  const router = createMemoryRouter(
    [
      {path: '/_embed/:embedSlug', element: <Widget />},
      {path: '/projects/:id', element: <h1>Project detail page</h1>},
    ],
    {initialEntries: ['/_embed/current-projects-widget']},
  );
  render(<RouterProvider router={router} />);
  return router;
};

const setUserActivation = (value: {isActive: boolean} | undefined) =>
  Object.defineProperty(window.navigator, 'userActivation', {configurable: true, value});

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
    expect(screen.queryByRole('button', {name: /Blocked:/})).toBeNull();
  });

  it('keeps search changes inside the widget', () => {
    const open = vi.spyOn(window, 'open');
    renderWidget();

    fireEvent.click(screen.getByRole('button', {name: 'Next page'}));

    expect(screen.getByTestId('location')).toHaveTextContent('/_embed/current-projects-widget?page=2');
    expect(open).not.toHaveBeenCalled();
  });

  it('hands back the URL when the browser blocks the tab, until it is cleared', () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const router = renderWidget();

    fireEvent.click(screen.getByRole('link', {name: 'Project ABC'}));

    const fallback = screen.getByRole('button', {
      name: `Blocked: ${window.location.origin}/projects/abc?tab=team#members`,
    });
    expect(router.state.location.pathname).toBe('/_embed/current-projects-widget');

    fireEvent.click(fallback);
    expect(screen.queryByRole('button', {name: /Blocked:/})).toBeNull();
  });

  it('does not open a tab without a user gesture (e.g. a redirect on load)', () => {
    setUserActivation({isActive: false});
    const open = vi.spyOn(window, 'open');
    renderWidget();

    fireEvent.click(screen.getByRole('link', {name: 'Project ABC'}));

    expect(open).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: /Blocked: .*\/projects\/abc/})).toBeInTheDocument();
  });
});
