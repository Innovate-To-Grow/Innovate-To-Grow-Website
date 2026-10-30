import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
    PROJECT_GRID_PAGE_SIZE_OPTIONS,
    useProjectGridTable,
} from '@/features/projects/components/grid/state/useProjectGridTable';
import {REMOTE_SEARCH_DELAY_MS} from '@/features/projects/components/grid/state/useRemoteSearchMatches';
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

    it('filters rows through the deferred search value', async () => {
        const rows = makeItems(makeRows());
        const {result} = renderHook(() =>
            useProjectGridTable({rows, defaultSortField: 'semester_label'}),
        );

        act(() => result.current.setSearch('project 2'));

        await waitFor(() => expect(result.current.filteredRows).toHaveLength(1));
        expect(result.current.filteredRows[0].project_title).toBe('Project 2');
    });

    it('keeps the rows the server finds by text they do not carry, along with their own matches', async () => {
        // Compact archive rows have no abstract; "EnergyPro" is only in Project 3's abstract on the server.
        const industries = ['Water', 'Energy', 'Food'];
        const rows = makeItems(
            makeRows(3).map((row, index) => ({...row, id: `p${index + 1}`, abstract: '', industry: industries[index]})),
        );
        const searchRemote = vi.fn(async (query: string) => new Set(query === 'energy' ? ['p1', 'p3'] : ['p3']));
        const {result} = renderHook(() =>
            useProjectGridTable({
                rows,
                defaultSortField: 'team_number',
                searchRemote,
                // The extra filter still applies to the server's matches.
                filterRow: (row) => row.project_title !== 'Project 1',
            }),
        );
        const titles = () => result.current.filteredRows.map((row) => row.project_title);

        act(() => result.current.setSearch('EnergyPro'));
        // Until the server answers, only the rows' own text has been searched.
        await waitFor(() => expect(result.current.search).toBe('EnergyPro'));
        expect(titles()).toEqual([]);
        expect(result.current.serverSearch.pending).toBe(true);

        await waitFor(() => expect(result.current.serverSearch.pending).toBe(false));
        expect(titles()).toEqual(['Project 3']);
        expect(searchRemote).toHaveBeenLastCalledWith('EnergyPro', expect.any(AbortSignal));

        // Project 2 matches by its own industry; Project 1 the server names, but the filter hides it.
        act(() => result.current.setSearch('energy'));
        await waitFor(() => expect(searchRemote).toHaveBeenLastCalledWith('energy', expect.any(AbortSignal)));
        await waitFor(() => expect(result.current.serverSearch.pending).toBe(false));
        expect(titles()).toEqual(['Project 2', 'Project 3']);
    });

    it('does not ask the server about a search every row already matches', async () => {
        // Every row's class is "Capstone": the server could not add a row.
        const rows = makeItems(
            makeRows(4).map((row, index) => ({...row, id: `p${index}`, abstract: '', class_code: 'CAP'})),
        );
        const searchRemote = vi.fn(async () => new Set(['p0']));
        const {result} = renderHook(() =>
            useProjectGridTable({
                rows,
                defaultSortField: 'team_number',
                searchRemote,
                classLabels: {CAP: 'Engineering Capstone'},
            }),
        );

        act(() => result.current.setSearch('capstone'));
        await waitFor(() => expect(result.current.search).toBe('capstone'));
        expect(result.current.serverSearch.pending).toBe(false);
        await act(() => new Promise((resolve) => setTimeout(resolve, REMOTE_SEARCH_DELAY_MS + 50)));
        expect(searchRemote).not.toHaveBeenCalled();
        expect(result.current.filteredRows).toHaveLength(4);
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

    it('finds rows by what the page shows, not by hidden or raw values', async () => {
        const rows = makeItems([
            makeRow({
                semester_label: '2026-2 Fall',
                class_code: 'CSE',
                team_number: '403',
                project_title: 'Carrot Field AI System',
                organization: 'Bolthouse Fresh Foods',
                student_names: 'Ana Živanović',
                is_presenting: 'Yes',
            }),
            makeRow({
                semester_label: '2026-2 Fall',
                class_code: 'CAP',
                team_number: '101',
                project_title: 'In-Air Drop "Shower-Head" Development',
                abstract: 'A drop apparatus.',
                is_presenting: 'No',
            }),
        ]);
        const {result} = renderHook(() =>
            useProjectGridTable({
                rows,
                defaultSortField: 'class_code',
                classLabels: {CSE: 'Software Engineering Capstone', CAP: 'Engineering Capstone'},
            }),
        );
        const titlesFor = async (search: string) => {
            act(() => result.current.setSearch(search));
            let titles: string[] = [];
            await waitFor(() => {
                expect(result.current.search).toBe(search);
                titles = result.current.filteredRows.map((row) => row.project_title);
            });
            return titles;
        };

        expect(await titlesFor('Fall 2026')).toHaveLength(2);
        expect(await titlesFor('Software Engineering')).toEqual(['Carrot Field AI System']);
        expect(await titlesFor('cap  101')).toEqual(['In-Air Drop "Shower-Head" Development']);
        expect(await titlesFor('CAP101')).toEqual(['In-Air Drop "Shower-Head" Development']);
        expect(await titlesFor('\u201cShower-Head\u201d')).toEqual(['In-Air Drop "Shower-Head" Development']);
        expect(await titlesFor('Bolthouse  Fresh')).toEqual(['Carrot Field AI System']);
        expect(await titlesFor('zivanovic')).toEqual(['Carrot Field AI System']);
        // The presenting flag is not shown, so it is not searched.
        expect(await titlesFor('yes')).toEqual([]);
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
