import {act, cleanup, render} from '@testing-library/react';
import {createMemoryRouter, Outlet, RouterProvider} from 'react-router';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {RouteDocumentTitle} from '@/app/router/RouteDocumentTitle';
import {usePageTitle} from '@/hooks/usePageTitle';

const NamedFromData = ({title, description}: {title: string | null; description?: string}) => {
  usePageTitle(title, {description});
  return null;
};

const meta = (selector: string) => document.head.querySelector<HTMLMetaElement>(selector)?.content ?? null;

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
          {path: 'list', element: <p>list</p>, handle: {title: 'Current Projects', description: 'Projects this semester.'}},
          {
            path: 'project',
            element: <NamedFromData title="A project" description="A drone that plants trees." />,
            handle: {description: 'Projects this semester.'},
          },
          {path: 'shared/:id', element: <p>shared</p>, handle: {title: 'Past Projects', noindex: true}},
        ],
      },
    ],
    {initialEntries: [initialPath]},
  );

describe('RouteDocumentTitle', () => {
  beforeEach(() => {
    document.head.innerHTML = '<meta name="description" content="The site.">';
    document.title = 'Innovate to Grow | School of Engineering';
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

    expect(document.title).toBe('Innovate to Grow | School of Engineering');
  });

  it('renames the tab when navigating back to a titled route', async () => {
    const router = buildRouter('/news');
    render(<RouterProvider router={router} />);

    await act(() => router.navigate('/cms'));
    document.title = 'About | Innovate to Grow';
    await act(() => router.navigate('/news'));

    expect(document.title).toBe('News | Innovate to Grow');
  });

  it("describes the page from its route, and the page's own description wins", async () => {
    const router = buildRouter('/list');
    render(<RouterProvider router={router} />);
    expect(meta('meta[name="description"]')).toBe('Projects this semester.');

    await act(() => router.navigate('/project'));
    expect(meta('meta[name="description"]')).toBe('A drone that plants trees.');

    await act(() => router.navigate('/cms'));
    expect(meta('meta[name="description"]')).toBe('The site.');
  });

  it('keeps routes marked noindex out of search indexes, and only those', async () => {
    const router = buildRouter('/shared/abc');
    render(<RouterProvider router={router} />);
    expect(meta('meta[name="robots"]')).toBe('noindex');

    await act(() => router.navigate('/list'));
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it('points the canonical URL and og:url at the page without its query string or fragment', async () => {
    const router = buildRouter('/list?q=solar#results');
    render(<RouterProvider router={router} />);

    const canonical = `${window.location.origin}/list`;
    expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute('href', canonical);
    expect(meta('meta[property="og:url"]')).toBe(canonical);

    await act(() => router.navigate('/news'));
    expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute('href', `${window.location.origin}/news`);
  });
});
