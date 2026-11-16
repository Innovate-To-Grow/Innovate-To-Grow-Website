import {vi} from 'vitest';

import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridRow,
  type ProjectGridSortDirection,
} from '@/features/projects/components/grid/contracts/projectGrid';

// Each test uses its own ids: loaded (or failed) details are kept per project between renders.
export const makeRows = (prefix: string, count: number, overrides: Partial<ProjectGridRow> = {}): ProjectGridItem[] =>
  createProjectGridItems(
    Array.from(
      {length: count},
      (_, index): ProjectGridRow => ({
        id: `${prefix}-${index}`,
        semester_label: '2025-1 Spring',
        class_code: 'CAP',
        team_number: `${index + 1}`,
        team_name: `Team ${index + 1}`,
        project_title: `Project ${index + 1}`,
        organization: 'Acme',
        industry: 'Energy',
        abstract: 'An abstract',
        student_names: 'Ada',
        is_presenting: '',
        ...overrides,
      }),
    ),
    prefix,
  );

export const rows = makeRows('states', 2);

export const baseProps = {
  columns: PAST_PROJECT_GRID_COLUMNS,
  rows,
  pagedRows: rows,
  filteredCount: 2,
  totalCount: 2,
  search: '',
  sortField: 'semester_label' as ProjectGridColumnKey,
  sortDirection: 'asc' as ProjectGridSortDirection,
  onSearchChange: vi.fn(),
  onSortChange: vi.fn(),
  expandedKeys: new Set<string>(),
  onToggleExpanded: vi.fn(),
  page: 0,
  totalPages: 1,
  onPageChange: vi.fn(),
  pageSize: 10,
  pageSizeOptions: [10, 25],
  onPageSizeChange: vi.fn(),
};

export const noRows = {rows: [], pagedRows: [], filteredCount: 0, totalCount: 0};

export const emptyState = {
  emptyTitle: 'No current projects yet',
  emptyMessage: "This semester's projects appear here once the schedule is published.",
  emptyActions: (
    <a className="itg-btn itg-btn-outline" href="/past-projects">
      Search Past Projects
    </a>
  ),
};
