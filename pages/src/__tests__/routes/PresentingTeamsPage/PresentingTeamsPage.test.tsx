import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import type {ReactNode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PresentingTeamsPage} from '@/routes/PresentingTeamsPage/PresentingTeamsPage';
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

describe('PresentingTeamsPage', () => {
  beforeEach(() => {
    viewProps.current = null;
    vi.mocked(useCurrentProjectGridData).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows only presenting teams, counted as teams', () => {
    vi.mocked(useCurrentProjectGridData).mockReturnValue({
      rows: [row({team_name: 'Presenter'}), row({id: 'p-2', team_name: 'NonPresenter', is_presenting: 'No'})],
      loading: false,
      error: null,
      refetch: vi.fn(),
      classLabels: {CAP: 'Engineering Capstone'},
    });

    render(
      <MemoryRouter>
        <PresentingTeamsPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Presenting Teams'})).toBeInTheDocument();
    const rows = viewProps.current?.rows as ProjectGridRow[];
    expect(rows.map((presenting) => presenting.team_name)).toEqual(['Presenter']);
    expect(viewProps.current).toMatchObject({
      title: 'Presenting Teams',
      namespace: 'presenting-teams',
      emptyTitle: 'No presenting teams yet',
      emptyMessage:
        "Teams appear here once this semester's showcase schedule is published. Older projects are in Past Projects.",
      countLabel: 'teams',
      classLabels: {CAP: 'Engineering Capstone'},
    });
    expect(String(viewProps.current?.lede)).toMatch(/^Teams presenting at this semester's Innovate to Grow showcase\./);

    cleanup();
    render(<MemoryRouter>{viewProps.current?.emptyActions as ReactNode}</MemoryRouter>);
    expect(screen.getByRole('link', {name: 'Search Past Projects'})).toHaveAttribute('href', '/past-projects');
  });

  it('forwards the loading and error state, and the reload for "Try again"', () => {
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
        <PresentingTeamsPage />
      </MemoryRouter>,
    );

    expect(viewProps.current).toMatchObject({loading: true, error: 'Failed to load', onRetry: refetch});
  });
});
