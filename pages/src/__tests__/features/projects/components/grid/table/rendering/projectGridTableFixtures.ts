import {vi} from 'vitest';

import {
    PAST_PROJECT_GRID_COLUMNS,
    createProjectGridItems,
    type ProjectGridColumnKey,
    type ProjectGridItem,
    type ProjectGridRow,
    type ProjectGridSortDirection,
} from '@/features/projects/components/grid/contracts/projectGrid';

export const makeRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
    semester_label: '2025-1 Spring',
    class_code: 'ENGR 120',
    team_number: 'T01',
    team_name: 'Team Alpha',
    project_title: 'Alpha Project',
    organization: 'Acme',
    industry: 'Technology',
    abstract: 'An abstract',
    student_names: 'Alice',
    is_presenting: '',
    ...overrides,
});

export const makeRows = (count = 2): ProjectGridItem[] =>
    createProjectGridItems(
        Array.from({length: count}, (_, index) =>
            makeRow({
                team_number: `T0${index + 1}`,
                team_name: `Team ${index + 1}`,
                project_title: `Project ${index + 1}`,
            }),
        ),
        'test',
    );

export const baseProps = {
    columns: PAST_PROJECT_GRID_COLUMNS,
    rows: makeRows(),
    pagedRows: makeRows(),
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
    pageSize: 5,
    pageSizeOptions: [5, 10, 25],
    onPageSizeChange: vi.fn(),
};
