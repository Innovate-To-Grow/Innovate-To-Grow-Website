import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
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
});
