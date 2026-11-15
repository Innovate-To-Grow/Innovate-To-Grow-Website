import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes} from 'react-router';

import {ProjectDetailPage} from '@/routes/projects/ProjectDetailPage/ProjectDetailPage';
import {fetchProjectDetail} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {
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

  it('shows the class and term, the team and organization, the facts in table order, and the team members', async () => {
    render(
      <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    // An archive project names its class as current projects do, and the term reads the same in both places.
    expect(await screen.findByText('Engineering Capstone · Spring 2025')).toHaveClass('itg-eyebrow');
    expect(screen.getByText('General Rotary · E&J Gallo Winery')).toHaveClass('itg-page-meta');
    const facts = screen.getAllByRole('term').map((term) => term.textContent);
    expect(facts).toEqual(['Term', 'Class', 'Team #', 'Team', 'Organization', 'Industry']);
    expect(screen.getAllByRole('definition').map((value) => value.textContent)).toEqual([
      'Spring 2025',
      'Engineering Capstone (CAP)',
      '101',
      'General Rotary',
      'E&J Gallo Winery',
      'Food Processing',
    ]);
    expect(screen.getByRole('heading', {level: 2, name: 'Abstract'})).toBeInTheDocument();
    const members = screen.getByRole('heading', {level: 2, name: 'Team members'}).closest('section') as HTMLElement;
    expect(within(members).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Alice', 'Bob']);
  });

  it('shows a team number stored with its class prefix without repeating the class', async () => {
    vi.mocked(fetchProjectDetail).mockResolvedValue({...projectDetail, team_number: 'CAP01', semester_label: '2021-1 Spring'});
    renderAt(`/past-projects/project/${projectDetail.id}`);

    const teamNumber = await screen.findByText('Team #');
    expect(teamNumber.nextElementSibling).toHaveTextContent(/^01$/);
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

      const copyButton = await screen.findByRole('button', {name: 'Copy Link to this project'});
      expect(copyButton.closest('article')).toHaveAttribute('data-launcher-avoid', '');
      expect(copyButton).toHaveClass('itg-btn', 'itg-btn-primary');
      // The back link beside it is an outline button, the same at every width.
      const backLinks = screen.getAllByRole('link', {name: /^back to /i});
      expect(backLinks[1]).toHaveClass('itg-btn', 'itg-btn-outline', 'project-detail-actions-back');
      fireEvent.click(copyButton);

      const status = await screen.findByRole('status');
      expect(status).toHaveTextContent('Link copied.');
      expect(status).toHaveClass('itg-success');
      expect(writeText).toHaveBeenCalledWith(window.location.href);
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('aborts and ignores a stale detail response after route navigation', async () => {
    const projectA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    const projectB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
    let resolveFirst!: (value: typeof projectDetail) => void;
    let resolveSecond!: (value: typeof projectDetail) => void;
    const first = new Promise<typeof projectDetail>((resolve) => {
      resolveFirst = resolve;
    });
    const second = new Promise<typeof projectDetail>((resolve) => {
      resolveSecond = resolve;
    });
    vi.mocked(fetchProjectDetail).mockImplementation((id) =>
      id === projectA ? first : second,
    );
    const router = createMemoryRouter(
      [{path: '/projects/:id', element: <ProjectDetailPage />}],
      {initialEntries: [`/projects/${projectA}`]},
    );
    render(<RouterProvider router={router} />);

    await waitFor(() =>
      expect(fetchProjectDetail).toHaveBeenCalledWith(
        projectA,
        expect.any(AbortSignal),
      ),
    );
    const firstSignal = vi.mocked(fetchProjectDetail).mock.calls[0][1];

    await act(async () => {
      await router.navigate(`/projects/${projectB}`);
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
