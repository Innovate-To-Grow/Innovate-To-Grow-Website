import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ProjectsPage} from '@/routes/ProjectsPage/ProjectsPage';
import {
  createProjectGridItems,
  useProjectGridTable,
  type ProjectGridItem,
  type ProjectGridRow,
} from '@/features/projects';
import {useCurrentProjectGridData} from '@/features/projects/hooks/useProjectGridData';

vi.mock('@/features/projects', () => ({
  PROJECT_GRID_COLUMNS: [{key: 'team_name', label: 'Team Name'}],
  ProjectGridTable: (props: Record<string, unknown>) => (
    <div
      data-testid="project-grid-table"
      data-empty-message={String(props.emptyMessage)}
      data-count-label={String(props.countLabel)}
      data-loading={String(props.loading)}
      data-error={String(props.error ?? '')}
      data-total-count={String(props.totalCount)}
    />
  ),
  createProjectGridItems: vi.fn(),
  useProjectGridTable: vi.fn(),
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

const tableResult = () => ({
  search: '',
  setSearch: vi.fn(),
  sortField: 'class_code' as const,
  sortDirection: 'asc' as const,
  toggleSort: vi.fn(),
  pageSize: 10,
  setPageSize: vi.fn(),
  pageSizeOptions: [5, 10, 25, 50, 100],
  page: 0,
  setPage: vi.fn(),
  totalPages: 1,
  filteredRows: [],
  sortedRows: [],
  selectedRows: [],
  pagedRows: [],
  expandedKeys: new Set<string>(),
  toggleExpanded: vi.fn(),
  selectedKeys: new Set<string>(),
  toggleSelected: vi.fn(),
  clearSelection: vi.fn(),
  selectAllRows: vi.fn(),
  selectRows: vi.fn(),
  toggleAllDetails: vi.fn(),
  allDetailsExpanded: false,
  hasSelection: false,
  removeSelectedRows: (rows: ProjectGridItem[]) => rows,
  keepSelectedRows: (rows: ProjectGridItem[]) => rows,
  fingerprints: new Set<string>(),
});

const gridData = (overrides: {rows?: ProjectGridRow[]; loading?: boolean; error?: string | null} = {}) => ({
  rows: [],
  loading: false,
  error: null,
  refetch: vi.fn(),
  ...overrides,
});

describe('ProjectsPage', () => {
  beforeEach(() => {
    vi.mocked(createProjectGridItems).mockReset();
    vi.mocked(useProjectGridTable).mockReset();
    vi.mocked(useCurrentProjectGridData).mockReset();
    vi.mocked(createProjectGridItems).mockImplementation((rows, namespace) =>
      rows.map((gridRow, index) => ({...gridRow, __key: `${namespace}-${index}`})),
    );
    vi.mocked(useProjectGridTable).mockReturnValue(tableResult());
    vi.mocked(useCurrentProjectGridData).mockReturnValue(gridData());
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the heading and lead copy', () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Current Projects'})).toBeInTheDocument();
    expect(
      screen.getByText(
        'Browse the current Innovate to Grow projects, search by team or organization, and expand rows to view abstracts and student names.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('project-grid-table')).toBeInTheDocument();
  });

  it('passes every current project row into the grid items', () => {
    vi.mocked(useCurrentProjectGridData).mockReturnValue(
      gridData({
        rows: [
          row({team_name: 'Presenter'}),
          row({
            id: '22222222-2222-4222-8222-222222222222',
            team_name: 'NonPresenter',
            is_presenting: 'No',
          }),
        ],
      }),
    );

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    const [rowsArg, namespaceArg] = vi.mocked(createProjectGridItems).mock.calls[0];
    expect(rowsArg).toHaveLength(2);
    expect(rowsArg.map((gridRow) => gridRow.team_name)).toEqual([
      'Presenter',
      'NonPresenter',
    ]);
    expect(namespaceArg).toBe('current-projects');
  });

  it('forwards empty message and count label to the table', () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    const table = screen.getByTestId('project-grid-table');
    expect(table.getAttribute('data-empty-message')).toBe(
      'No current projects are available yet.',
    );
    expect(table.getAttribute('data-count-label')).toBe('projects');
  });

  it('seeds the search box from the value query parameter', () => {
    render(
      <MemoryRouter initialEntries={['/current-projects?value=rocket']}>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(useProjectGridTable).toHaveBeenCalledWith(
      expect.objectContaining({initialSearch: 'rocket'}),
    );
  });
});
