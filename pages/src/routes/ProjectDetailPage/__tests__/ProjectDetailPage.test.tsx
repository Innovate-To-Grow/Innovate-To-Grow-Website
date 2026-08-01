import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes} from 'react-router';

import {ProjectDetailPage} from '../ProjectDetailPage';
import {fetchProjectDetail} from '@/features/projects/api';

vi.mock('@/features/projects/api', () => ({
  fetchProjectDetail: vi.fn(),
}));

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
    const backLink = screen.getByRole('link', {name: /back to past projects/i});
    expect(backLink.getAttribute('href')).toBe('/past-projects');
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
    const backLink = screen.getByRole('link', {name: /back to projects/i});
    expect(backLink.getAttribute('href')).toBe('/current-projects');
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

    expect(await screen.findByText('Unable to load this project.')).toBeInTheDocument();
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

    expect(await screen.findByText('Unable to load this project.')).toBeInTheDocument();
    const backLink = screen.getByRole('link', {name: /back to projects/i});
    expect(backLink.getAttribute('href')).toBe('/current-projects');
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
