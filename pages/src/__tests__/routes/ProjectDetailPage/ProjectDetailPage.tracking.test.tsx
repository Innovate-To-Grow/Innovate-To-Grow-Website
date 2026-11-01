import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {createMemoryRouter, Outlet, RouterProvider} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {RouteDocumentTitle} from '@/app/router/RouteDocumentTitle';
import {fetchCurrentSchedule} from '@/features/events/api';
import {fetchProjectDetail, type ProjectDetail} from '@/features/projects/api';
import {usePageTitle} from '@/hooks/usePageTitle';
import {usePageTracking} from '@/hooks/usePageTracking';
import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';

// Siteimprove records a client-side page view under the tab title it is sent with. A project page names the tab
// only once its project is back, and the view waits for that; these go through the real page and route titles,
// from each kind of page a visitor opens a project from.

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  trackPageView: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: vi.fn(),
}));

const PROJECT_ID = '11111111-1111-4111-8111-111111111111';

const projectDetail: ProjectDetail = {
  id: PROJECT_ID,
  project_title: 'Rotary Joint Testing System',
  team_name: 'General Rotary',
  team_number: '101',
  organization: 'E&J Gallo Winery',
  industry: 'Food Processing',
  abstract: 'A detailed abstract.',
  student_names: 'Alice, Bob',
  class_code: 'CAP',
  track: null,
  presentation_order: null,
  semester_label: '2025 Spring',
};

const ORIGIN = window.location.origin;

/** The page shell (Container): it tracks the page it holds, after the page's own effects. */
const Shell = () => {
  usePageTracking();
  return <Outlet />;
};

/** A CMS page names the tab from its data (useCMSPageDocument). */
const CmsPage = () => {
  usePageTitle('Judges');
  return <h1>Judges</h1>;
};

/** The app's order: the route's title (RouteDocumentTitle), then the shell around the page. */
const renderApp = (initialEntry: string) => {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <>
            <RouteDocumentTitle />
            <Shell />
          </>
        ),
        children: [
          {path: 'current-projects', element: <h1>Current Projects</h1>, handle: {title: 'Current Projects'}},
          {path: 'presenting-teams', element: <h1>Presenting Teams</h1>, handle: {title: 'Presenting Teams'}},
          {path: 'past-projects', element: <h1>Past Projects</h1>, handle: {title: 'Past Projects'}},
          {path: 'projects/:id', element: <ProjectDetailPage />},
          {path: 'past-projects/project/:id', element: <ProjectDetailPage />},
          {path: '*', element: <CmsPage />},
        ],
      },
    ],
    {initialEntries: [initialEntry]},
  );
  render(<RouterProvider router={router} />);
  return router;
};

describe('ProjectDetailPage page views', () => {
  let push: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    push = vi.fn();
    (window as {_sz?: unknown})._sz = {push};
    document.title = 'Innovate to Grow | School of Engineering';
    window.requestIdleCallback = ((callback: (deadline: IdleDeadline) => void) => {
      callback({didTimeout: false, timeRemaining: () => 50});
      return 1;
    }) as unknown as Window['requestIdleCallback'];
    window.cancelIdleCallback = vi.fn();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    // No schedule is published: /projects/:id reads the archive.
    vi.mocked(fetchCurrentSchedule).mockReset();
    vi.mocked(fetchCurrentSchedule).mockRejectedValue({response: {status: 404}});
    vi.mocked(fetchProjectDetail).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    delete (window as {_sz?: unknown})._sz;
    delete (window as {requestIdleCallback?: unknown}).requestIdleCallback;
    delete (window as {cancelIdleCallback?: unknown}).cancelIdleCallback;
  });

  it.each([
    ['Presenting Teams', '/presenting-teams', `/projects/${PROJECT_ID}`],
    ['a CMS page', '/judges', `/projects/${PROJECT_ID}`],
    ['Current Projects', '/current-projects', `/projects/${PROJECT_ID}`],
    ['Past Projects', '/past-projects', `/past-projects/project/${PROJECT_ID}`],
  ])('sends the view of a project opened from %s with the project title', async (_from, from, to) => {
    let answer!: (detail: ProjectDetail) => void;
    vi.mocked(fetchProjectDetail).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const router = renderApp(from);
    // The landing view is counted by Siteimprove itself.
    await waitFor(() => expect(document.title).not.toBe('Innovate to Grow | School of Engineering'));
    expect(push).not.toHaveBeenCalled();

    await act(() => router.navigate(to));
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    await waitFor(() => expect(fetchProjectDetail).toHaveBeenCalled());
    // Not under the title of the page the visitor came from, nor under a section's name.
    expect(push).not.toHaveBeenCalled();

    await act(async () => answer(projectDetail));
    await waitFor(() => expect(push).toHaveBeenCalledOnce());
    expect(push).toHaveBeenCalledWith([
      'trackdynamic',
      {url: `${ORIGIN}${to}`, title: 'Rotary Joint Testing System | Innovate to Grow'},
    ]);
  });
});
