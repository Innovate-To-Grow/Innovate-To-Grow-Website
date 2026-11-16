import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {
    PROJECT_GRID_PAGE_SIZE_OPTIONS,
    useProjectGridTable,
} from '@/features/projects/components/grid/state/useProjectGridTable';
import {createProjectGridItems, type ProjectGridItem, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const makeRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
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

const makeRows = (count = 3): ProjectGridRow[] =>
    Array.from({length: count}, (_, index) =>
        makeRow({
            team_number: `T0${index + 1}`,
            team_name: `Team ${index + 1}`,
            project_title: `Project ${index + 1}`,
        }),
    );

const makeItems = (rows: ProjectGridRow[]): ProjectGridItem[] => createProjectGridItems(rows, 'test');

describe('useProjectGridTable', () => {
    afterEach(() => {
        cleanup();
    });

    it('returns the initial state with the configured sort and page size', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        expect(result.current.search).toBe('');
        expect(result.current.sortField).toBe('semester_label');
        expect(result.current.sortDirection).toBe('asc');
        expect(result.current.page).toBe(0);
        expect(result.current.pageSize).toBe(10);
        expect(result.current.pageSizeOptions).toEqual([5, 10, 25, 50, 100]);
        expect(result.current.filteredRows).toHaveLength(3);
        expect(result.current.sortedRows).toHaveLength(3);
        expect(result.current.pagedRows).toHaveLength(3);
    });

    it('toggles sort direction when the same field is clicked twice', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.toggleSort('semester_label'));
        expect(result.current.sortDirection).toBe('desc');

        act(() => result.current.toggleSort('semester_label'));
        expect(result.current.sortDirection).toBe('asc');
    });

    it('switches to a new sort field in ascending order', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({
                rows,
                defaultSortField: 'semester_label',
                defaultSortDirection: 'desc',
            }),
        );

        act(() => result.current.toggleSort('project_title'));
        expect(result.current.sortField).toBe('project_title');
        expect(result.current.sortDirection).toBe('asc');
        expect(result.current.page).toBe(0);
    });

    it('sets a sort field and direction at once and goes back to the first page', () => {
        const rows = makeItems(makeRows(12));
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'class_code', pageSize: 5}),
        );

        act(() => result.current.setPage(2));
        act(() => result.current.setSort('project_title', 'desc'));

        expect(result.current.sortField).toBe('project_title');
        expect(result.current.sortDirection).toBe('desc');
        expect(result.current.page).toBe(0);
        expect(result.current.pagedRows[0].project_title).toBe('Project 12');
    });

    it('builds fingerprints for the current rows', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        expect(result.current.fingerprints.size).toBe(3);
    });

    it('includes the configured page size choices', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({
                rows,
                defaultSortField: 'semester_label',
                pageSizeOptions: [2, 4],
            }),
        );

        expect(result.current.pageSizeOptions).toEqual([2, 4, 10]);
        expect(PROJECT_GRID_PAGE_SIZE_OPTIONS).toEqual([5, 10, 25, 50, 100]);
    });
});
