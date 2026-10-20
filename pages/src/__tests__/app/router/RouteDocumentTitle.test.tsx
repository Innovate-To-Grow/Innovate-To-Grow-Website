import {act, cleanup, render} from '@testing-library/react';
import {createMemoryRouter, Outlet, RouterProvider} from 'react-router';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {RouteDocumentTitle} from '@/app/router/RouteDocumentTitle';
import {usePageTitle} from '@/hooks/usePageTitle';

const NamedFromData = ({title}: {title: string | null}) => {
  usePageTitle(title);
  return null;
};

const buildRouter = (initialPath: string) =>
  createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <>
            <RouteDocumentTitle />
            <Outlet />
          </>
        ),
        children: [
          {path: 'news', element: <p>news</p>, handle: {title: 'News'}},
          {path: 'story', element: <NamedFromData title="A story" />, handle: {title: 'News'}},
          {path: 'loading', element: <NamedFromData title={null} />},
          {path: 'cms', element: <p>cms</p>},
        ],
      },
    ],
    {initialEntries: [initialPath]},
  );

describe('RouteDocumentTitle', () => {
  beforeEach(() => {
    document.title = 'Innovate To Grow | School of Engineering';
  });

  afterEach(cleanup);

  it('names the tab after the matched route', () => {
    render(<RouterProvider router={buildRouter('/news')} />);

    expect(document.title).toBe('News | Innovate to Grow');
  });

  it("lets a page name itself from its data over the route's title", () => {
    render(<RouterProvider router={buildRouter('/story')} />);

    expect(document.title).toBe('A story | Innovate to Grow');
  });

  it('leaves the title alone on routes without one', () => {
    render(<RouterProvider router={buildRouter('/loading')} />);

    expect(document.title).toBe('Innovate To Grow | School of Engineering');
  });

  it('renames the tab when navigating back to a titled route', async () => {
    const router = buildRouter('/news');
    render(<RouterProvider router={router} />);

    await act(() => router.navigate('/cms'));
    document.title = 'About | Innovate to Grow';
    await act(() => router.navigate('/news'));

    expect(document.title).toBe('News | Innovate to Grow');
  });
});
