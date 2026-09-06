import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {
    PROJECT_GRID_PAGE_SIZE_OPTIONS,
    useProjectGridTable,
} from '@/features/projects/components/useProjectGridTable';
import {createProjectGridItems, type ProjectGridItem, type ProjectGridRow} from '@/features/projects/components/projectGrid';

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

    it('filters rows through the deferred search value', async () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.setSearch('project 2'));

        await waitFor(() => expect(result.current.filteredRows).toHaveLength(1));
        expect(result.current.filteredRows[0].project_title).toBe('Project 2');
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

    it('expands and collapses a row', () => {
        const rows = makeItems(makeRows());
        const rowKey = rows[0].__key;
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.toggleExpanded(rowKey));
        expect(result.current.expandedKeys.has(rowKey)).toBe(true);

        act(() => result.current.toggleExpanded(rowKey));
        expect(result.current.expandedKeys.has(rowKey)).toBe(false);
    });

    it('selects and unselects rows, tracking hasSelection', () => {
        const rows = makeItems(makeRows());
        const rowKey = rows[0].__key;
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        expect(result.current.hasSelection).toBe(false);

        act(() => result.current.toggleSelected(rowKey));
        expect(result.current.selectedKeys.has(rowKey)).toBe(true);
        expect(result.current.hasSelection).toBe(true);

        act(() => result.current.toggleSelected(rowKey));
        expect(result.current.selectedKeys.has(rowKey)).toBe(false);
        expect(result.current.hasSelection).toBe(false);
    });

    it('selects all rows, clears them, and selects a filtered subset', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.selectAllRows());
        expect(result.current.selectedKeys.size).toBe(3);

        act(() => result.current.selectRows(rows.slice(0, 2)));
        expect(result.current.selectedKeys.size).toBe(2);

        act(() => result.current.clearSelection());
        expect(result.current.selectedKeys.size).toBe(0);
    });

    it('expands all details and then collapses them', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.toggleAllDetails());
        expect(result.current.allDetailsExpanded).toBe(true);
        expect(result.current.expandedKeys.size).toBe(3);

        act(() => result.current.toggleAllDetails());
        expect(result.current.allDetailsExpanded).toBe(false);
        expect(result.current.expandedKeys.size).toBe(0);
    });

    it('keeps and removes selected rows from a source list', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.toggleSelected(rows[0].__key));

        expect(result.current.keepSelectedRows(rows).map((row) => row.project_title)).toEqual(['Project 1']);
        expect(result.current.removeSelectedRows(rows).map((row) => row.project_title)).toEqual([
            'Project 2',
            'Project 3',
        ]);
    });

    it('changes page size, floors it to an integer, resets the page, and merges the size into options', () => {
        const rows = makeItems(makeRows(20));
        const {result} = renderHook(() =>
            useProjectGridTable({rows, pageSize: 5, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.setPage(2));
        expect(result.current.page).toBe(2);

        act(() => result.current.setPageSize(3.9));
        expect(result.current.pageSize).toBe(3);
        expect(result.current.page).toBe(0);
        expect(result.current.pageSizeOptions).toContain(3);
    });

    it('never allows a page size below one', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, pageSize: 5, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.setPageSize(0));
        expect(result.current.pageSize).toBe(1);
    });

    it('clamps an out-of-range page back to the last page when rows shrink', () => {
        const rows = makeItems(makeRows(20));
        const {result, rerender} = renderHook(
            ({rows}: {rows: ProjectGridItem[]}) =>
                useProjectGridTable({rows, pageSize: 5, defaultSortField: 'semester_label'}),
            {initialProps: {rows}},
        );

        act(() => result.current.setPage(3));
        expect(result.current.page).toBe(3);

        // Shrink to a single page while the page index points past the last page.
        rerender({rows: makeItems(makeRows(2))});

        expect(result.current.page).toBe(0);
        expect(result.current.totalPages).toBe(1);
    });

    it('prunes expanded and selected keys for rows that no longer exist', () => {
        const rows = makeItems(makeRows());
        const rowKey = rows[0].__key;
        const {result, rerender} = renderHook(
            ({rows}: {rows: ProjectGridItem[]}) =>
                useProjectGridTable({rows, defaultSortField: 'semester_label'}),
            {initialProps: {rows}},
        );

        act(() => result.current.toggleExpanded(rowKey));
        act(() => result.current.toggleSelected(rowKey));
        expect(result.current.expandedKeys.has(rowKey)).toBe(true);
        expect(result.current.selectedKeys.has(rowKey)).toBe(true);

        // Replace the rows with a single, entirely different row so the previously
        // expanded/selected key no longer exists in the new list.
        rerender({rows: makeItems([makeRow({team_number: 'T99', project_title: 'Different Project'})])});

        expect(result.current.expandedKeys.size).toBe(0);
        expect(result.current.selectedKeys.size).toBe(0);
    });

    it('resets the search when the initialSearch prop changes', async () => {
        const rows = makeItems(makeRows());
        const {result, rerender} = renderHook(
            ({initialSearch}: {initialSearch: string}) =>
                useProjectGridTable({
                    rows,
                    defaultSortField: 'semester_label',
                    initialSearch,
                }),
            {initialProps: {initialSearch: ''}},
        );

        act(() => result.current.setSearch('manual'));
        await waitFor(() => expect(result.current.search).toBe('manual'));

        rerender({initialSearch: 'reset'});
        await waitFor(() => expect(result.current.search).toBe('reset'));
    });

    it('seeds expandable rows open when expandAllByDefault is set', async () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label', expandAllByDefault: true}),
        );

        await waitFor(() => expect(result.current.expandedKeys.size).toBe(3));
        expect(result.current.allDetailsExpanded).toBe(true);
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
