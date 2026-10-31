import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import type {ReactNode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ProjectsPage} from '@/routes/ProjectsPage/ProjectsPage';
import type {ProjectGridRow} from '@/features/projects';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

const viewProps = vi.hoisted(() => ({current: null as Record<string, unknown> | null}));

vi.mock('@/features/projects/components/views/pages/CurrentProjectsView', () => ({
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
      emptyTitle: 'No current projects yet',
      emptyMessage:
        "This semester's projects appear here once the schedule is published. Older projects are in Past Projects.",
      countLabel: 'projects',
    });
    expect(String(viewProps.current?.lede)).toMatch(/^Browse this semester's Innovate to Grow projects\./);
  });

  it('offers Past Projects as the one outline action of the empty state', () => {
    vi.mocked(useCurrentProjectGridData).mockReturnValue({
      rows: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
      classLabels: {},
    });
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );
    cleanup();

    render(<MemoryRouter>{viewProps.current?.emptyActions as ReactNode}</MemoryRouter>);
    const link = screen.getByRole('link', {name: 'Search Past Projects'});
    expect(link).toHaveAttribute('href', '/past-projects');
    expect(link).toHaveClass('itg-btn', 'itg-btn-outline');
  });

  it('forwards the loading and error state, and the reload for "Try Again"', () => {
    const refetch = vi.fn();
    vi.mocked(useCurrentProjectGridData).mockReturnValue({
      rows: [],
      loading: true,
      error: 'Failed to load',
      refetch,
      classLabels: {},
    });

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(viewProps.current).toMatchObject({loading: true, error: 'Failed to load', onRetry: refetch});
  });
});
