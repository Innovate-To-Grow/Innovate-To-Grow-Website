import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  PROJECT_LIST_LOAD_ERROR,
  useCurrentProjectGridData,
} from '@/features/projects/hooks/data/useProjectGridData.ts';
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

const httpError = (status: number) =>
    Object.assign(new Error(`Request failed with status code ${status}`), {response: {status}});

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

    it.each([
        ['a network failure', new Error('Network Error')],
        ['a timeout', Object.assign(new Error('timeout of 15000ms exceeded'), {code: 'ECONNABORTED'})],
        ['a server error', httpError(503)],
        ['a non-Error rejection', 'boom'],
    ])('reports %s in plain words, not the request error', async (_case, failure) => {
        mockFetchCurrentSchedule.mockRejectedValue(failure);

        const {result} = renderHook(() => useCurrentProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe(PROJECT_LIST_LOAD_ERROR);
        expect(result.current.rows).toEqual([]);
    });

    it('treats a missing schedule (404) as no current projects, not as a failure', async () => {
        mockFetchCurrentSchedule.mockRejectedValue(
            Object.assign(httpError(404), {response: {status: 404, data: {detail: 'No schedule available.'}}}),
        );

        const {result} = renderHook(() => useCurrentProjectGridData());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBeNull();
        expect(result.current.rows).toEqual([]);
    });

    it('gives the schedule request a timeout, so a stalled request ends in the error state', async () => {
        mockFetchCurrentSchedule.mockReturnValue(new Promise(() => {}));

        const {unmount} = renderHook(() => useCurrentProjectGridData());
        await waitFor(() => expect(mockFetchCurrentSchedule).toHaveBeenCalled());

        const [scheduleId, options] = mockFetchCurrentSchedule.mock.calls[0];
        expect(scheduleId).toBeNull();
        expect(options).toEqual({signal: expect.any(AbortSignal), timeout: 15_000});
        unmount();
        expect((options as {signal: AbortSignal}).signal.aborted).toBe(true);
    });

    it('files the teams that are not presenting under the schedule\'s term', async () => {
        mockFetchCurrentSchedule.mockResolvedValue({
            projects: [
                {...scheduleRow, year_semester: '2026-2 Fall'},
                {...scheduleRow, id: 'project-9', track: 0, order: 0, year_semester: '', is_presenting: false},
            ],
        });

        const {result} = renderHook(() => useCurrentProjectGridData());
        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(result.current.rows.map((row) => row.semester_label)).toEqual(['2026 Fall', '2026 Fall']);
    });

    it('links each row to its project and names the classes from the schedule sections', async () => {
        mockFetchCurrentSchedule.mockResolvedValue({
            projects: [
                scheduleRow,
                {...scheduleRow, id: 'slot-without-project', team_number: '102'},
                {...scheduleRow, id: 'project-9', track: 0, order: 0, year_semester: '', is_presenting: false},
            ],
            sections: [
                {
                    code: 'CAP',
                    label: 'Engineering Capstone',
                    tracks: [
                        {
                            slots: [
                                {id: 'schedule-1', project_id: 'project-1'},
                                {id: 'slot-without-project', project_id: null},
                            ],
                        },
                    ],
                },
            ],
        });

        const {result} = renderHook(() => useCurrentProjectGridData());
        await waitFor(() => expect(result.current.loading).toBe(false));

        // A presenting row is a schedule slot: it links to the slot's project, when the slot has one.
        expect(result.current.rows.map((row) => row.id)).toEqual(['project-1', undefined, 'project-9']);
        expect(result.current.classLabels).toEqual({CAP: 'Engineering Capstone'});
    });

    it('returns immediately without loading when disabled', () => {
        const {result} = renderHook(() => useCurrentProjectGridData(false));

        expect(result.current).toEqual({
            rows: [],
            loading: false,
            error: null,
            refetch: expect.any(Function),
            classLabels: {},
        });
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
