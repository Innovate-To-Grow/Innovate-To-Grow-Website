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
    expect(screen.getByRole('heading', {level: 1}).closest('section')).toHaveAttribute('data-launcher-avoid', '');
    // One primary action, then a text link.
    const search = screen.getByRole('link', {name: 'Search Past Projects'});
    expect(search).toHaveAttribute('href', '/past-projects');
    expect(search).toHaveClass('itg-btn', 'itg-btn-primary');
    const current = screen.getByRole('link', {name: 'Current Projects'});
    expect(current).toHaveAttribute('href', '/current-projects');
    expect(current).toHaveClass('itg-link');
    expect(screen.getByRole('link', {name: /back to current projects/i})).toHaveAttribute('href', '/current-projects');
    expect(screen.queryByRole('button', {name: 'Try Again'})).toBeNull();
    // The mark is claimed in an effect, which can run after the heading that findByRole saw.
    await waitFor(() =>
      expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex'),
    );
  });

  it.each([
    ['/projects', '22222222-2222-4222-8222-222222222222'],
    ['/projects', 'archive'],
    ['/past-projects/project', '22222222-2222-4222-8222-222222222222'],
    ['/past-projects/project', 'not-a-project'],
  ])('keeps an unknown project at %s/%s out of search results', async (prefix, id) => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    // Not the title an earlier case left: this page has to set it.
    document.title = 'Innovate to Grow | School of Engineering';
    renderAt(`${prefix}/${id}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
    // The title and the mark are set in effects, which can run after the heading that findByRole saw.
    await waitFor(() => expect(document.title).toBe('Project not found | Innovate to Grow'));
    await waitFor(() =>
      expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex'),
    );
    cleanup();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
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

    // Any failure but a 404 lands here, a server error included: the copy does not blame the visitor's connection.
    expect(
      await screen.findByText(
        'Unable to load this project. Please try again, or search for it by title, team or organization.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/connection/i)).toBeNull();
    expect(screen.getByRole('heading', {level: 1, name: "We couldn't load this project"})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {name: 'Rotary Joint Testing System'})).toBeNull();
    const backLink = screen.getByRole('link', {name: /back to past projects/i});
    expect(backLink.getAttribute('href')).toBe('/past-projects');
    // Try Again is the page's one primary action; the ways out are text links.
    expect(screen.getByRole('button', {name: 'Try Again'})).toHaveClass('itg-btn', 'itg-btn-primary');
    const search = screen.getByRole('link', {name: 'Search Past Projects'});
    expect(search).toHaveAttribute('href', '/past-projects');
    expect(search).toHaveClass('itg-link');
    expect(search).not.toHaveClass('itg-btn');
    expect(screen.getByRole('link', {name: 'Current Projects'})).toHaveClass('itg-link');
    // The two links wrap as one group, so a phone never leaves one alone under the button and the other.
    const links = search.parentElement as HTMLElement;
    expect(links).toHaveClass('project-detail-error-links');
    expect(links).toContainElement(screen.getByRole('link', {name: 'Current Projects'}));
    expect(links.previousElementSibling).toBe(screen.getByRole('button', {name: 'Try Again'}));
  });

  it('keeps a failed load out of search results until a retry loads the project', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValueOnce(new Error('boom')).mockResolvedValue(projectDetail);
    renderAt(`/past-projects/project/${projectDetail.id}`);
    const robots = () => document.head.querySelector('meta[name="robots"]');

    // The mark is claimed and withdrawn in effects, which can run after the DOM change findByRole saw.
    const tryAgain = await screen.findByRole('button', {name: 'Try Again'});
    await waitFor(() => expect(robots()).toHaveAttribute('content', 'noindex'));
    fireEvent.click(tryAgain);

    expect(await screen.findByRole('heading', {level: 1, name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    await waitFor(() => expect(robots()).toBeNull());
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
    expect(screen.getAllByRole('term').map((term) => term.textContent)).toEqual([
      'Term',
      'Class',
      'Team #',
      'Team',
      'Organization',
      'Industry',
      'Showcase',
    ]);
    expect(screen.getAllByRole('definition').map((value) => value.textContent)).toEqual([
      'Spring 2026',
      'Engineering Capstone (CAP)',
      '101',
      'HVAC Regulators',
      'ASHRAE - Sierra Delta',
      'Energy',
      'Track 1 · 1:00 · Glacier 165',
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
    expect(screen.getByText('Showcase').nextElementSibling).toHaveTextContent(/^Not presenting$/);
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

  it.each(['/projects/archive', '/projects/past', '/past-projects/project/archive', '/projects/..%2Fpast-shares'])(
    'says %s is not a project, without requesting the list endpoint its name matches',
    async (path) => {
      renderAt(path);

      expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
      expect(fetchCurrentSchedule).not.toHaveBeenCalled();
      expect(fetchProjectDetail).not.toHaveBeenCalled();
    },
  );

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

    fireEvent.click(screen.getByRole('button', {name: 'Try Again'}));

    expect(
      await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'}),
    ).toBeInTheDocument();
    expect(fetchCurrentSchedule).toHaveBeenCalledTimes(2);
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
