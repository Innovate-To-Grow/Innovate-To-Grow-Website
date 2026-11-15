import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

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

    it("goes back to the first page once when the server's answer adds rows to a search paged through", async () => {
        // 6 rows match "solar" by title (3 pages of 2); the server also finds two rows by their abstracts.
        const rows = makeItems(
            makeRows(12).map((row, index) => ({
                ...row,
                id: `p${index}`,
                abstract: '',
                project_title: index < 6 ? `Solar ${index}` : `Wind ${index}`,
            })),
        );
        let answer!: (ids: ReadonlySet<string>) => void;
        const searchRemote = vi.fn(() => new Promise<ReadonlySet<string>>((resolve) => (answer = resolve)));
        const {result, rerender} = renderHook(
            ({items}) => useProjectGridTable({rows: items, pageSize: 2, defaultSortField: 'team_number', searchRemote}),
            {initialProps: {items: rows}},
        );

        act(() => result.current.setSearch('solar'));
        await waitFor(() => expect(searchRemote).toHaveBeenCalledTimes(1));
        // The visitor pages on before the answer arrives.
        act(() => result.current.setPage(2));
        expect(result.current.pagedRows.map((row) => row.project_title)).toEqual(['Solar 4', 'Solar 5']);

        await act(async () => answer(new Set(['p6', 'p7'])));
        expect(result.current.filteredRows).toHaveLength(8);
        // Page 3 would now hold other rows under the same "showing 5–6": the search starts over.
        expect(result.current.page).toBe(0);

        // Rows removed later do not start it over again.
        act(() => result.current.setPage(2));
        rerender({items: rows.filter((row) => row.id !== 'p6')});
        expect(result.current.page).toBe(2);
    });

    it('starts over again only when an answer adds other rows, not when the same rows come back', async () => {
        const rows = makeItems(
            makeRows(12).map((row, index) => ({
                ...row,
                id: `p${index}`,
                abstract: '',
                project_title: index < 6 ? `Solar ${index}` : `Wind ${index}`,
            })),
        );
        const answers: ((ids: ReadonlySet<string>) => void)[] = [];
        const searchRemote = vi.fn(() => new Promise<ReadonlySet<string>>((resolve) => answers.push(resolve)));
        const {result} = renderHook(() =>
            useProjectGridTable({rows, pageSize: 2, defaultSortField: 'team_number', searchRemote}),
        );
        /** The visitor takes a letter off the search and types it again: the last answer shows at once, and the
         *  server is asked again once typing pauses. */
        const retype = async () => {
            const asked = searchRemote.mock.calls.length;
            act(() => result.current.setSearch('sola'));
            act(() => result.current.setSearch('solar'));
            await waitFor(() => expect(result.current.filteredRows.length).toBeGreaterThan(6));
            await waitFor(() => expect(searchRemote).toHaveBeenCalledTimes(asked + 1));
        };

        act(() => result.current.setSearch('solar'));
        await waitFor(() => expect(searchRemote).toHaveBeenCalledTimes(1));
        await act(async () => answers[0](new Set(['p6', 'p7'])));
        expect(result.current.page).toBe(0);

        // The same rows, asked for again: a page the visitor moved to meanwhile stays.
        await retype();
        act(() => result.current.setPage(2));
        await act(async () => answers[1](new Set(['p7', 'p6'])));
        expect(result.current.page).toBe(2);

        // Another row the second time: it sorts in among the rows shown, so the search starts over.
        await retype();
        act(() => result.current.setPage(2));
        await act(async () => answers[2](new Set(['p6', 'p7', 'p8'])));
        expect(result.current.filteredRows).toHaveLength(9);
        expect(result.current.page).toBe(0);
    });

    it("keeps the page when the server's answer adds no rows", async () => {
        const rows = makeItems(
            makeRows(12).map((row, index) => ({
                ...row,
                id: `p${index}`,
                abstract: '',
                project_title: index < 6 ? `Solar ${index}` : 'Wind',
            })),
        );
        let answer!: (ids: ReadonlySet<string>) => void;
        const searchRemote = vi.fn(() => new Promise<ReadonlySet<string>>((resolve) => (answer = resolve)));
        const {result} = renderHook(() =>
            useProjectGridTable({rows, pageSize: 2, defaultSortField: 'team_number', searchRemote}),
        );

        act(() => result.current.setSearch('solar'));
        await waitFor(() => expect(searchRemote).toHaveBeenCalledTimes(1));
        act(() => result.current.setPage(2));
        // The server names only rows the titles already found.
        await act(async () => answer(new Set(['p0', 'p1'])));
        expect(result.current.serverSearch.pending).toBe(false);
        expect(result.current.page).toBe(2);
    });
});
