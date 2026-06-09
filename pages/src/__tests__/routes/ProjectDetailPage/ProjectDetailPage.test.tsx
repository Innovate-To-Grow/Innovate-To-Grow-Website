import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';
import type {ProjectDetail} from '@/features/projects/api';

const projectDetailMocks = vi.hoisted(() => ({
  fetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/projects/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/api')>('@/features/projects/api');
  return {
    ...actual,
    fetchProjectDetail: projectDetailMocks.fetchProjectDetail,
  };
});

const project: ProjectDetail = {
  id: 'project-1',
  project_title: 'Water Robot',
  team_name: 'Team Aqua',
  team_number: '123',
  organization: 'UC Merced',
  industry: 'Agriculture',
  abstract: 'A robot for irrigation.',
  student_names: 'Ada Lovelace, Grace Hopper',
  class_code: 'CSE',
  track: 1,
  presentation_order: 2,
  semester_label: '2026-1 Spring',
};

const renderProject = () =>
  render(
    <MemoryRouter initialEntries={['/projects/project-1']}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('ProjectDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    projectDetailMocks.fetchProjectDetail.mockResolvedValue(project);
  });

  it('renders project detail metadata and sections', async () => {
    renderProject();

    await waitFor(() => expect(projectDetailMocks.fetchProjectDetail).toHaveBeenCalledWith('project-1'));
    expect(await screen.findByRole('heading', {name: 'Water Robot'})).toBeInTheDocument();
    expect(screen.getByText('2026 Spring')).toBeInTheDocument();
    expect(screen.getByText('Team Aqua')).toBeInTheDocument();
    expect(screen.getByText('A robot for irrigation.')).toBeInTheDocument();
    expect(screen.getByText('Ada Lovelace, Grace Hopper')).toBeInTheDocument();
  });

  it('renders an error state when detail loading fails', async () => {
    projectDetailMocks.fetchProjectDetail.mockRejectedValueOnce(new Error('offline'));

    renderProject();

    expect(await screen.findByText('Unable to load this project.')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /Back to Projects/})).toHaveAttribute('href', '/current-projects');
  });
});
