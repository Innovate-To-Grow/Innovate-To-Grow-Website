import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {
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

    it('starts a new search on the first page, for every table that uses the hook', () => {
        const rows = makeItems(makeRows(25));
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label', pageSize: 5}),
        );

        act(() => result.current.setPage(3));
        expect(result.current.page).toBe(3);

        // Matches every row: page 4 would still exist, but the first matches are on page 1.
        act(() => result.current.setSearch('project'));
        expect(result.current.page).toBe(0);

        act(() => result.current.setPage(2));
        act(() => result.current.setSearch(''));
        expect(result.current.page).toBe(0);
    });

    it('starts from a restored sort and page, and keeps the page while the rows are still loading', () => {
        const {result, rerender} = renderHook(
            ({rows}: {rows: ProjectGridItem[]}) =>
                useProjectGridTable({
                    rows,
                    pageSize: 5,
                    defaultSortField: 'class_code',
                    initialSortField: 'project_title',
                    initialSortDirection: 'desc',
                    initialPage: 2,
                }),
            {initialProps: {rows: [] as ProjectGridItem[]}},
        );

        expect(result.current.sortField).toBe('project_title');
        expect(result.current.sortDirection).toBe('desc');
        // No rows yet: page 1 is all there is to show, but the restored page is not forgotten.
        expect(result.current.page).toBe(0);

        rerender({rows: makeItems(makeRows(25))});
        expect(result.current.page).toBe(2);
        expect(result.current.pagedRows[0].project_title).toBe('Project 15');
    });
});
