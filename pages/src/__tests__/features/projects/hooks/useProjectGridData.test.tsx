import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
    useCurrentProjectGridData,
    usePastProjectGridData,
    usePastProjectShareData,
} from '@/features/projects/hooks/useProjectGridData';
import type {CompactPastProjectRow, PaginatedResponse, PastProjectShare} from '@/features/projects/api';

const {mockFetchPastProjectArchive, mockFetchPastProjectShare, mockFetchCurrentSchedule} = vi.hoisted(() => ({
    mockFetchPastProjectArchive: vi.fn(),
    mockFetchPastProjectShare: vi.fn(),
    mockFetchCurrentSchedule: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/api')>();
    return {
        ...actual,
        fetchPastProjectArchive: (...args: unknown[]) => mockFetchPastProjectArchive(...args),
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

const makePage = (
    results: CompactPastProjectRow[],
    count = results.length,
): PaginatedResponse<CompactPastProjectRow> => ({
    count,
    next: null,
    previous: null,
    results,
});

describe('usePastProjectGridData', () => {
    afterEach(() => {
        mockFetchPastProjectArchive.mockReset();
    });

    it('keeps serving the previous rows, without flipping loading, while a refetch is in flight', async () => {
        let resolveSecond: (projects: PaginatedResponse<CompactPastProjectRow>) => void = () => {
        };
        mockFetchPastProjectArchive
            .mockResolvedValueOnce({
                count: 1,
                next: null,
                previous: null,
                results: [makeProject({project_title: 'First Load'})]
            })
            .mockImplementationOnce(
                () =>
                    new Promise<PaginatedResponse<CompactPastProjectRow>>((resolve) => {
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
            resolveSecond({
                count: 2,
                next: null,
                previous: null,
                results: [
                    makeProject({project_title: 'First Load'}),
                    makeProject({id: 'project-2', project_title: 'Second Load'}),
                ],
            });
        });

        await waitFor(() =>
            expect(result.current.rows.map((row) => row.project_title)).toEqual(['First Load', 'Second Load']),
        );
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('paginates until every archive row is collected', async () => {
        mockFetchPastProjectArchive
            .mockResolvedValueOnce(makePage([makeProject({}), makeProject({id: 'p-2'})], 3))
            .mockResolvedValueOnce(makePage([makeProject({id: 'p-3'})], 3));

        const {result} = renderHook(() => usePastProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(mockFetchPastProjectArchive).toHaveBeenCalledTimes(2);
        expect(result.current.rows).toHaveLength(3);
        expect(result.current.error).toBeNull();
    });

    it('surfaces an Error message and clears rows', async () => {
        mockFetchPastProjectArchive.mockRejectedValue(new Error('offline'));

        const {result} = renderHook(() => usePastProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('offline');
        expect(result.current.rows).toEqual([]);
    });

    it('falls back to a generic message for non-Error rejections', async () => {
        mockFetchPastProjectArchive.mockRejectedValue('network down');

        const {result} = renderHook(() => usePastProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('Failed to load past projects');
    });

    it('returns immediately without loading when disabled', () => {
        const {result} = renderHook(() => usePastProjectGridData(false));

        expect(result.current).toEqual({rows: [], loading: false, error: null, refetch: expect.any(Function)});
        expect(mockFetchPastProjectArchive).not.toHaveBeenCalled();
    });

    it('aborts the in-flight archive request on unmount', async () => {
        mockFetchPastProjectArchive.mockReturnValue(new Promise(() => {}));

        const {unmount} = renderHook(() => usePastProjectGridData());
        await waitFor(() => expect(mockFetchPastProjectArchive).toHaveBeenCalled());
        unmount();

        const signal = mockFetchPastProjectArchive.mock.calls[0][1] as AbortSignal;
        expect(signal.aborted).toBe(true);
    });
});

describe('useCurrentProjectGridData', () => {
    afterEach(() => {
        mockFetchCurrentSchedule.mockReset();
    });

    const scheduleRow = {
        id: 'schedule-1',
        track: 1,
        order: 2,
        year_semester: '2025-1 Spring',
        class_code: 'CAP',
        team_number: '101',
        team_name: 'Solar Team',
        project_title: 'Solar Project',
        organization: 'Solar Org',
        industry: 'Energy',
        abstract: 'An abstract',
        student_names: 'Alex',
        is_presenting: true,
        tooltip: '',
    };

    it('loads current schedule projects through the row mapper', async () => {
        mockFetchCurrentSchedule.mockResolvedValue({projects: [scheduleRow]});

        const {result} = renderHook(() => useCurrentProjectGridData());

        expect(result.current.loading).toBe(true);
        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(result.current.error).toBeNull();
        expect(result.current.rows).toEqual([
            expect.objectContaining({semester_label: '2025 Spring', is_presenting: 'Yes'}),
        ]);
    });

    it('surfaces errors from the current schedule fetch', async () => {
        mockFetchCurrentSchedule.mockRejectedValue(new Error('schedule down'));

        const {result} = renderHook(() => useCurrentProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('schedule down');
        expect(result.current.rows).toEqual([]);
    });

    it('falls back to a generic message for non-Error rejections', async () => {
        mockFetchCurrentSchedule.mockRejectedValue('boom');

        const {result} = renderHook(() => useCurrentProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('Failed to load current projects');
    });

    it('returns immediately without loading when disabled', () => {
        const {result} = renderHook(() => useCurrentProjectGridData(false));

        expect(result.current).toEqual({rows: [], loading: false, error: null, refetch: expect.any(Function)});
        expect(mockFetchCurrentSchedule).not.toHaveBeenCalled();
    });

    it('refetches on demand and serves stale rows in between', async () => {
        mockFetchCurrentSchedule.mockResolvedValueOnce({projects: [scheduleRow]});
        let resolveSecond: (payload: {projects: typeof scheduleRow[]}) => void = () => {};
        mockFetchCurrentSchedule.mockImplementationOnce(
            () => new Promise<{projects: typeof scheduleRow[]}>((resolve) => {
                resolveSecond = resolve;
            }),
        );

        const {result} = renderHook(() => useCurrentProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        act(() => result.current.refetch());

        // The current-projects hook has no stale-while-revalidate: a refetch flips loading back on
        // and clears rows until the fresh response lands.
        expect(result.current.loading).toBe(true);
        expect(result.current.rows).toHaveLength(0);

        await act(async () => {
            resolveSecond({projects: [scheduleRow, {...scheduleRow, id: 'schedule-2'}]});
        });

        await waitFor(() => expect(result.current.rows).toHaveLength(2));
        expect(result.current.loading).toBe(false);
    });
});

describe('usePastProjectShareData', () => {
    afterEach(() => {
        mockFetchPastProjectShare.mockReset();
    });

    const makeShare = (overrides: Partial<PastProjectShare> = {}): PastProjectShare => ({
        id: 'share-1',
        name: 'Shared',
        rows: [],
        note: '',
        details_text: '',
        version: 1,
        share_url: 'https://example.test/share-1',
        can_edit: false,
        created_at: '2026-08-12T00:00:00Z',
        ...overrides,
    });

    it('returns null share without loading when no share id is provided', () => {
        const {result} = renderHook(() => usePastProjectShareData(undefined));

        expect(result.current).toEqual({share: null, loading: false, error: null});
        expect(mockFetchPastProjectShare).not.toHaveBeenCalled();
    });

    it('loads a share by id', async () => {
        mockFetchPastProjectShare.mockResolvedValue(makeShare());

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        expect(result.current.loading).toBe(true);
        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(result.current.error).toBeNull();
        expect(result.current.share).toMatchObject({id: 'share-1', name: 'Shared'});
    });

    it('surfaces an Error message', async () => {
        mockFetchPastProjectShare.mockRejectedValue(new Error('not found'));

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('not found');
        expect(result.current.share).toBeNull();
    });

    it('falls back to a generic message for non-Error rejections', async () => {
        mockFetchPastProjectShare.mockRejectedValue('denied');

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('Failed to load shared past projects');
    });

    it('ignores a late resolution after unmount', async () => {
        let resolve!: (share: PastProjectShare) => void;
        mockFetchPastProjectShare.mockReturnValue(
            new Promise<PastProjectShare>((res) => {
                resolve = res;
            }),
        );

        const {unmount} = renderHook(() => usePastProjectShareData('share-1'));
        await waitFor(() => expect(mockFetchPastProjectShare).toHaveBeenCalled());
        unmount();

        await act(async () => {
            resolve(makeShare());
        });
    });
});
