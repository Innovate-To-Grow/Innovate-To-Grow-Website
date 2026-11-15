import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes} from 'react-router';

import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';
import {fetchProjectDetail} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {
  HVAC_PROJECT_ID,
  currentSchedulePayload,
} from '@/__tests__/features/projects/fixtures/currentSchedule';

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: vi.fn(),
}));

const notFoundError = () => Object.assign(new Error('Request failed with status code 404'), {response: {status: 404}});

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
        <Route path="/past-projects/project/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

const projectDetail = {
  id: '11111111-1111-4111-8111-111111111111',
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

describe('ProjectDetailPage', () => {
  beforeEach(() => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockResolvedValue(projectDetail);
    // The schedule of this semester, which has none of the archive ids used below.
    vi.mocked(fetchCurrentSchedule).mockReset();
    vi.mocked(fetchCurrentSchedule).mockResolvedValue(currentSchedulePayload());
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('uses the Past Projects back link on individual past project routes', async () => {
    render(
      <MemoryRouter initialEntries={[`/past-projects/project/${projectDetail.id}`]}>
        <Routes>
          <Route path="/past-projects/project/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    // One back link above the title and one under the page.
    const backLinks = screen.getAllByRole('link', {name: /back to past projects/i});
    expect(backLinks).toHaveLength(2);
    backLinks.forEach((link) => expect(link.getAttribute('href')).toBe('/past-projects'));
    expect(fetchProjectDetail).toHaveBeenCalledWith(
      projectDetail.id,
      expect.any(AbortSignal),
    );
  });

  it('points an archive project on the legacy project route back to Past Projects', async () => {
    render(
      <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    const backLinks = screen.getAllByRole('link', {name: /back to past projects/i});
    expect(backLinks).toHaveLength(2);
    backLinks.forEach((link) => expect(link.getAttribute('href')).toBe('/past-projects'));
  });

  it('goes back to the list that opened the project, as the visitor left it', async () => {
    const router = createMemoryRouter(
      [
        {path: '/presenting-teams', element: <h1>Presenting Teams list</h1>},
        {path: '/projects/:id', element: <ProjectDetailPage />},
      ],
      {
        initialEntries: [
          '/presenting-teams?class=CAP&page=2',
          {pathname: `/projects/${HVAC_PROJECT_ID}`, state: {from: '/presenting-teams?class=CAP&page=2'}},
        ],
        initialIndex: 1,
      },
    );
    render(<RouterProvider router={router} />);

    await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'});
    const backLinks = screen.getAllByRole('link', {name: /back to presenting teams/i});
    expect(backLinks).toHaveLength(2);
    backLinks.forEach((link) => expect(link).toHaveAttribute('href', '/presenting-teams?class=CAP&page=2'));

    fireEvent.click(backLinks[1]);

    expect(await screen.findByRole('heading', {name: 'Presenting Teams list'})).toBeInTheDocument();
    // History Back, not a new entry: the list comes back with its scroll position.
    expect(router.state.historyAction).toBe('POP');
    expect(router.state.location.search).toBe('?class=CAP&page=2');
  });

  it('follows the back link instead when it is opened with a modifier key', async () => {
    const router = createMemoryRouter([{path: '/projects/:id', element: <ProjectDetailPage />}], {
      initialEntries: [{pathname: `/projects/${HVAC_PROJECT_ID}`, state: {from: '/current-projects?sort=organization'}}],
    });
    render(<RouterProvider router={router} />);

    const [backLink] = await screen.findAllByRole('link', {name: /back to current projects/i});
    expect(backLink).toHaveAttribute('href', '/current-projects?sort=organization');
    const click = new MouseEvent('click', {bubbles: true, cancelable: true, ctrlKey: true});
    backLink.dispatchEvent(click);
    // Left to the browser (a new tab), not taken over by the page.
    expect(click.defaultPrevented).toBe(false);
    expect(router.state.location.pathname).toBe(`/projects/${HVAC_PROJECT_ID}`);
  });

  it.each([{from: '/news'}, {from: '//example.com/current-projects'}, {from: 42}, 'not-an-object'])(
    'ignores link state that names no project list (%j)',
    async (state) => {
      const router = createMemoryRouter([{path: '/projects/:id', element: <ProjectDetailPage />}], {
        initialEntries: [{pathname: `/projects/${HVAC_PROJECT_ID}`, state}],
      });
      render(<RouterProvider router={router} />);

      const backLinks = await screen.findAllByRole('link', {name: /back to current projects/i});
      backLinks.forEach((link) => expect(link).toHaveAttribute('href', '/current-projects'));
    },
  );

  it('names the tab after the project, or after what went wrong', async () => {
    renderAt(`/projects/${HVAC_PROJECT_ID}`);
    await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'});
    await waitFor(() => expect(document.title).toBe('ASHRAE HVAC Design Calculations | Innovate to Grow'));
    cleanup();

    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt('/past-projects/project/00000000-0000-4000-8000-000000000000');
    await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"});
    await waitFor(() => expect(document.title).toBe('Project not found | Innovate to Grow'));
    cleanup();

    renderAt('/projects/archive');
    await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"});
    await waitFor(() => expect(document.title).toBe('Project not found | Innovate to Grow'));
    cleanup();

    vi.mocked(fetchProjectDetail).mockRejectedValue(new Error('boom'));
    renderAt(`/past-projects/project/${projectDetail.id}`);
    await screen.findByRole('heading', {level: 1, name: "We couldn't load this project"});
    await waitFor(() => expect(document.title).toBe("Project couldn't be loaded | Innovate to Grow"));
  });
});
