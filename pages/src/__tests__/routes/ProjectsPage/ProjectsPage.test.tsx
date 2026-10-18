import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ProjectsPage} from '@/routes/ProjectsPage/ProjectsPage';
import type {ProjectGridRow} from '@/features/projects';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

const viewProps = vi.hoisted(() => ({current: null as Record<string, unknown> | null}));

vi.mock('@/features/projects/components/CurrentProjectsView', () => ({
  CurrentProjectsView: (props: Record<string, unknown>) => {
    viewProps.current = props;
    return <h1>{String(props.title)}</h1>;
  },
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
  useCurrentProjectGridData: vi.fn(),
}));

const row = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
  id: '11111111-1111-4111-8111-111111111111',
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Team Alpha',
  project_title: 'Project Title',
  organization: 'Acme',
  industry: 'Technology',
  abstract: 'Abstract.',
  student_names: 'Alice, Bob',
  is_presenting: 'Yes',
  ...overrides,
});

describe('ProjectsPage', () => {
  beforeEach(() => {
    viewProps.current = null;
    vi.mocked(useCurrentProjectGridData).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders every current project (presenting or not) through the current-projects view', () => {
    const rows = [row({team_name: 'Presenter'}), row({id: 'p-2', team_name: 'NonPresenter', is_presenting: 'No'})];
    const classLabels = {CAP: 'Engineering Capstone'};
    vi.mocked(useCurrentProjectGridData).mockReturnValue({
      rows,
      loading: false,
      error: null,
      refetch: vi.fn(),
      classLabels,
    });

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Current Projects'})).toBeInTheDocument();
    expect(viewProps.current).toMatchObject({
      title: 'Current Projects',
      rows,
      classLabels,
      loading: false,
      error: null,
      namespace: 'current-projects',
      emptyMessage: 'No current projects are available yet.',
      countLabel: 'projects',
    });
    expect(String(viewProps.current?.lede)).toMatch(/^Browse this semester's Innovate to Grow projects\./);
  });

  it('forwards the loading and error state', () => {
    vi.mocked(useCurrentProjectGridData).mockReturnValue({
      rows: [],
      loading: true,
      error: 'Failed to load',
      refetch: vi.fn(),
      classLabels: {},
    });

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(viewProps.current).toMatchObject({loading: true, error: 'Failed to load'});
  });
});
