import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {usePastProjectGridData} from '@/features/projects/hooks/useProjectGridData';
import type {CompactPastProjectRow, PaginatedResponse} from '@/features/projects/api';

const mockFetchPastProjectArchive = vi.fn();

vi.mock('@/features/projects/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/api')>();
    return {
        ...actual,
        fetchPastProjectArchive: (...args: unknown[]) => mockFetchPastProjectArchive(...args),
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
});
