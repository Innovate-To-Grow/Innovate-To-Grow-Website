import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes} from 'react-router';

import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';
import {fetchProjectDetail} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {
  HVAC_PROJECT_ID,
  HVAC_SLOT_ID,
  WING_PROJECT_ID,
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

  it('keeps the current-projects back link on the legacy project route', async () => {
    render(
      <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    const backLinks = screen.getAllByRole('link', {name: /back to current projects/i});
    expect(backLinks).toHaveLength(2);
    backLinks.forEach((link) => expect(link.getAttribute('href')).toBe('/current-projects'));
  });

  it('shows the class and term, the team and organization, the facts in table order, and the team members', async () => {
    render(
      <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('CAP · Spring 2025')).toHaveClass('itg-eyebrow');
    expect(screen.getByText('General Rotary · E&J Gallo Winery')).toHaveClass('itg-page-meta');
    const facts = screen.getAllByRole('term').map((term) => term.textContent);
    expect(facts).toEqual(['Term', 'Class', 'Team #', 'Team', 'Organization', 'Industry']);
    expect(screen.getAllByRole('definition').map((value) => value.textContent)).toEqual([
      '2025 Spring',
      'CAP',
      '101',
      'General Rotary',
      'E&J Gallo Winery',
      'Food Processing',
    ]);
    expect(screen.getByRole('heading', {level: 2, name: 'Abstract'})).toBeInTheDocument();
    const members = screen.getByRole('heading', {level: 2, name: 'Team members'}).closest('section') as HTMLElement;
    expect(within(members).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Alice', 'Bob']);
  });

  it('copies the link to the project and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      render(
        <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
          <Routes>
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
          </Routes>
        </MemoryRouter>,
      );

      fireEvent.click(await screen.findByRole('button', {name: 'Copy link to this project'}));

      expect(await screen.findByRole('status')).toHaveTextContent('Link copied.');
      expect(writeText).toHaveBeenCalledWith(window.location.href);
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('explains a project that does not exist and offers a search', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue({response: {status: 404}});
    render(
      <MemoryRouter initialEntries={['/projects/missing']}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
    expect(screen.getByText(/The link may be incomplete, or the project has been removed/)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Search past projects'})).toHaveAttribute('href', '/past-projects');
    expect(screen.getByRole('link', {name: 'Current Projects'})).toHaveAttribute('href', '/current-projects');
    expect(screen.getByRole('link', {name: /back to current projects/i})).toHaveAttribute('href', '/current-projects');
    expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
  });

  it('shows an error message with the Past Projects back link when the fetch fails', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(new Error('boom'));
    render(
      <MemoryRouter initialEntries={[`/past-projects/project/${projectDetail.id}`]}>
        <Routes>
          <Route path="/past-projects/project/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Unable to load this project\./)).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 1, name: "We couldn't load this project"})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {name: 'Rotary Joint Testing System'})).toBeNull();
    const backLink = screen.getByRole('link', {name: /back to past projects/i});
    expect(backLink.getAttribute('href')).toBe('/past-projects');
  });

  it('shows the current-projects back link on the error branch of the legacy route', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(new Error('boom'));
    render(
      <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Unable to load this project\./)).toBeInTheDocument();
    const backLink = screen.getByRole('link', {name: /back to current projects/i});
    expect(backLink.getAttribute('href')).toBe('/current-projects');
  });

  it('shows a current project from the schedule, by the id Current Projects links to', async () => {
    // As in production, the archive does not know current-semester ids.
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${HVAC_PROJECT_ID}`);

    expect(
      await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'}),
    ).toBeInTheDocument();
    expect(screen.getByText('Engineering Capstone · Spring 2026')).toHaveClass('itg-eyebrow');
    expect(screen.getByText('HVAC Regulators · ASHRAE - Sierra Delta')).toHaveClass('itg-page-meta');
    expect(screen.getAllByRole('definition').map((value) => value.textContent)).toEqual([
      '2026 Spring',
      'Engineering Capstone (CAP)',
      '101',
      'HVAC Regulators',
      'ASHRAE - Sierra Delta',
      'Energy',
    ]);
    expect(screen.getByText(/^This project aimed to design a complete HVAC system/)).toHaveClass(
      'project-detail-abstract',
    );
    const members = screen.getByRole('heading', {level: 2, name: 'Team members'}).closest('section') as HTMLElement;
    expect(within(members).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Brian Arroyo',
      'Joel Gonzalez',
      'Kyle On',
      'Manuel Cruz Cavero',
    ]);
    const backLinks = screen.getAllByRole('link', {name: /back to current projects/i});
    expect(backLinks).toHaveLength(2);
    backLinks.forEach((link) => expect(link).toHaveAttribute('href', '/current-projects'));
    expect(screen.queryByRole('heading', {name: "We couldn't find this project"})).toBeNull();
    expect(fetchProjectDetail).not.toHaveBeenCalled();
  });

  it('shows a current team that is not presenting, with the term of the schedule', async () => {
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${WING_PROJECT_ID}`);

    expect(
      await screen.findByRole('heading', {level: 1, name: 'Distributed-Flapping Wing with Glide-Lock Mechanism'}),
    ).toBeInTheDocument();
    expect(screen.getByText('Engineering Capstone · Spring 2026')).toHaveClass('itg-eyebrow');
    expect(screen.getByText('Abstract-201')).toBeInTheDocument();
    // No student names on this row: no empty Team members section.
    expect(screen.queryByRole('heading', {name: 'Team members'})).toBeNull();
  });

  it('falls back to the archive for an archive id on /projects/:id', async () => {
    renderAt(`/projects/${projectDetail.id}`);

    expect(await screen.findByRole('heading', {name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    expect(fetchCurrentSchedule).toHaveBeenCalledTimes(1);
    expect(fetchProjectDetail).toHaveBeenCalledWith(projectDetail.id, expect.any(AbortSignal));
  });

  it('reads only the archive on past-project pages, even for an id the schedule has', async () => {
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/past-projects/project/${HVAC_PROJECT_ID}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
    expect(fetchCurrentSchedule).not.toHaveBeenCalled();
  });

  it('does not take a schedule slot id for a project', async () => {
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${HVAC_SLOT_ID}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
  });

  it('offers to try again, instead of calling the link wrong, when the schedule cannot be read', async () => {
    vi.mocked(fetchCurrentSchedule).mockRejectedValueOnce(new Error('Network Error'));
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${HVAC_PROJECT_ID}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't load this project"})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {name: "We couldn't find this project"})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: 'Try again'}));

    expect(
      await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'}),
    ).toBeInTheDocument();
    expect(fetchCurrentSchedule).toHaveBeenCalledTimes(2);
  });

  it('aborts and ignores a stale detail response after route navigation', async () => {
    let resolveFirst!: (value: typeof projectDetail) => void;
    let resolveSecond!: (value: typeof projectDetail) => void;
    const first = new Promise<typeof projectDetail>((resolve) => {
      resolveFirst = resolve;
    });
    const second = new Promise<typeof projectDetail>((resolve) => {
      resolveSecond = resolve;
    });
    vi.mocked(fetchProjectDetail).mockImplementation((id) =>
      id === 'project-a' ? first : second,
    );
    const router = createMemoryRouter(
      [{path: '/projects/:id', element: <ProjectDetailPage />}],
      {initialEntries: ['/projects/project-a']},
    );
    render(<RouterProvider router={router} />);

    await waitFor(() =>
      expect(fetchProjectDetail).toHaveBeenCalledWith(
        'project-a',
        expect.any(AbortSignal),
      ),
    );
    const firstSignal = vi.mocked(fetchProjectDetail).mock.calls[0][1];

    await act(async () => {
      await router.navigate('/projects/project-b');
    });
    resolveSecond({...projectDetail, project_title: 'Project B'});
    expect(
      await screen.findByRole('heading', {name: 'Project B'}),
    ).toBeInTheDocument();

    resolveFirst({...projectDetail, project_title: 'Project A'});
    await act(async () => {
      await Promise.resolve();
    });

    expect(firstSignal?.aborted).toBe(true);
    expect(
      screen.getByRole('heading', {name: 'Project B'}),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', {name: 'Project A'}),
    ).toBeNull();
  });
});
