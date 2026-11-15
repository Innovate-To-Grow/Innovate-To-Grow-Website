import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {PROJECT_LIST_LOAD_ERROR, usePastProjectGridData} from '@/features/projects/hooks/useProjectGridData';
import type {CompactPastProjectRow, PaginatedResponse} from '@/features/projects/api';

const {mockFetchPastProjectArchive} = vi.hoisted(() => ({mockFetchPastProjectArchive: vi.fn()}));

vi.mock('@/features/projects/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/api')>();
    return {
        ...actual,
        // The hook loads every archive page through fetchAllPastProjectArchive; one mocked page stands for them all.
        fetchAllPastProjectArchive: async (...args: unknown[]) =>
            ((await mockFetchPastProjectArchive(...args)) as PaginatedResponse<CompactPastProjectRow>).results,
    };
});

const page = (titles: string[]): PaginatedResponse<CompactPastProjectRow> => ({
    count: titles.length,
    next: null,
    previous: null,
    results: titles.map((project_title, index) => ({
        id: `project-${index}`,
        semester_label: '2025-1 Spring',
        class_code: 'CAP',
        team_number: `${index}`,
        team_name: `Team ${index}`,
        project_title,
        organization: 'Org',
        industry: 'Energy',
        track: null,
        presentation_order: null,
    })),
});

describe('usePastProjectGridData — a refetch that fails', () => {
    afterEach(() => {
        mockFetchPastProjectArchive.mockReset();
    });

    it('keeps serving the rows it was revalidating, next to the error', async () => {
        mockFetchPastProjectArchive
            .mockResolvedValueOnce(page(['First Load']))
            .mockRejectedValueOnce(new Error('Request failed with status code 503'))
            .mockResolvedValueOnce(page(['First Load', 'Second Load']));

        const {result} = renderHook(() => usePastProjectGridData());
        await waitFor(() => expect(result.current.loading).toBe(false));
        const firstRows = result.current.rows;

        act(() => result.current.refetch());
        await waitFor(() => expect(result.current.error).toBe(PROJECT_LIST_LOAD_ERROR));
        // The same rows (same array): consumers keep their search tables and see no new archive.
        expect(result.current.rows).toBe(firstRows);
        expect(result.current.loading).toBe(false);

        // Trying again clears the error while it runs and replaces the rows when it succeeds.
        act(() => result.current.refetch());
        expect(result.current.error).toBeNull();
        await waitFor(() =>
            expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load', 'Second Load']),
        );
        expect(result.current.error).toBeNull();
    });

    it('reports loading while retrying a first load that failed, since it has no rows to serve meanwhile', async () => {
        let resolveRetry!: (payload: PaginatedResponse<CompactPastProjectRow>) => void;
        mockFetchPastProjectArchive
            .mockRejectedValueOnce(new Error('Network Error'))
            .mockImplementationOnce(() => new Promise((resolve) => { resolveRetry = resolve; }));

        const {result} = renderHook(() => usePastProjectGridData());
        await waitFor(() => expect(result.current.error).toBe(PROJECT_LIST_LOAD_ERROR));
        expect(result.current.loading).toBe(false);

        act(() => result.current.refetch());
        // Consumers show their loading state rather than empty tables that would never pick up the archive.
        expect(result.current.loading).toBe(true);
        expect(result.current.error).toBeNull();

        await act(async () => resolveRetry(page(['Recovered'])));
        expect(result.current.loading).toBe(false);
        expect(result.current.rows.map((row) => row.project_title)).toEqual(['Recovered']);
    });
});
