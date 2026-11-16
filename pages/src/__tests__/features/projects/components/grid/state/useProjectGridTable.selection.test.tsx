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

    it('selects a subset of rows and clears them', () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.selectRows(rows));
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
});
