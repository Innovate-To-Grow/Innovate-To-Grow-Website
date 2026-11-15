import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  PROJECT_LIST_LOAD_ERROR,
  usePastProjectGridData,
} from '@/features/projects/hooks/useProjectGridData';
import type {CompactPastProjectRow} from '@/features/projects/api';

const {mockFetchAllPastProjectArchive, mockFetchPastProjectShare, mockFetchCurrentSchedule} = vi.hoisted(() => ({
    mockFetchAllPastProjectArchive: vi.fn(),
    mockFetchPastProjectShare: vi.fn(),
    mockFetchCurrentSchedule: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/api')>();
    return {
        ...actual,
        fetchAllPastProjectArchive: (...args: unknown[]) => mockFetchAllPastProjectArchive(...args),
        fetchPastProjectShare: (...args: unknown[]) => mockFetchPastProjectShare(...args),
    };
});

vi.mock('@/features/events/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/events/api')>();
    return {
        ...actual,
        fetchCurrentSchedule: (...args: unknown[]) => mockFetchCurrentSchedule(...args),
    };
});

const makeProject = (overrides: Partial<CompactPastProjectRow>): CompactPastProjectRow => ({
    id: 'project-1',
    semester_label: '2025-1 Spring',
    class_code: 'CAP',
    team_number: '101',
    team_name: 'Solar Team',
    project_title: 'Solar Project',
    organization: 'Solar Org',
    industry: 'Energy',
    track: null,
    presentation_order: null,
    ...overrides,
});

const httpError = (status: number) =>
    Object.assign(new Error(`Request failed with status code ${status}`), {response: {status}});

describe('usePastProjectGridData', () => {
    afterEach(() => {
        mockFetchAllPastProjectArchive.mockReset();
    });

    it('keeps serving the previous rows, without flipping loading, while a refetch is in flight', async () => {
        let resolveSecond: (projects: CompactPastProjectRow[]) => void = () => {
        };
        mockFetchAllPastProjectArchive
            .mockResolvedValueOnce([makeProject({project_title: 'First Load'})])
            .mockImplementationOnce(
                () =>
                    new Promise<CompactPastProjectRow[]>((resolve) => {
                        resolveSecond = resolve;
                    }),
            );

        const {result} = renderHook(() => usePastProjectGridData());

        expect(result.current.loading).toBe(true);
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load']);

        act(() => result.current.refetch());

        // Stale-while-revalidate: the previous rows stay available and there is no loading flash,
        // so consumers keep their search tables (and per-table curation) mounted across a refresh.
        expect(result.current.loading).toBe(false);
        expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load']);

        await act(async () => {
            resolveSecond([
                makeProject({project_title: 'First Load'}),
                makeProject({id: 'project-2', project_title: 'Second Load'}),
            ]);
        });

        await waitFor(() =>
            expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load', 'Second Load']),
        );
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('loads the whole archive and maps it to grid rows', async () => {
        mockFetchAllPastProjectArchive.mockResolvedValue([
            makeProject({}),
            makeProject({id: 'p-2', student_names: 'Brian Arroyo'}),
        ]);

        const {result} = renderHook(() => usePastProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(mockFetchAllPastProjectArchive).toHaveBeenCalledTimes(1);
        expect(mockFetchAllPastProjectArchive).toHaveBeenCalledWith({}, expect.any(AbortSignal));
        expect(result.current.rows.map((row) => [row.id, row.semester_label, row.student_names])).toEqual([
            ['project-1', '2025 Spring', ''],
            ['p-2', '2025 Spring', 'Brian Arroyo'],
        ]);
        expect(result.current.error).toBeNull();
    });

    it.each([
        ['a network failure', new Error('Network Error')],
        ['a server error', httpError(500)],
        ['a non-Error rejection', 'network down'],
    ])('reports %s in plain words and clears rows', async (_case, failure) => {
        mockFetchAllPastProjectArchive.mockRejectedValue(failure);

        const {result} = renderHook(() => usePastProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe(PROJECT_LIST_LOAD_ERROR);
        expect(result.current.rows).toEqual([]);
    });

    it('returns immediately without loading when disabled', () => {
        const {result} = renderHook(() => usePastProjectGridData(false));

        expect(result.current).toEqual({rows: [], loading: false, error: null, refetch: expect.any(Function)});
        expect(mockFetchAllPastProjectArchive).not.toHaveBeenCalled();
    });

    it('aborts the in-flight archive request on unmount', async () => {
        mockFetchAllPastProjectArchive.mockReturnValue(new Promise(() => {}));

        const {unmount} = renderHook(() => usePastProjectGridData());
        await waitFor(() => expect(mockFetchAllPastProjectArchive).toHaveBeenCalled());
        unmount();

        const signal = mockFetchAllPastProjectArchive.mock.calls[0][1] as AbortSignal;
        expect(signal.aborted).toBe(true);
    });
});
