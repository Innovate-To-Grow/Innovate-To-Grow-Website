import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  usePastProjectShareData,
} from '@/features/projects/hooks/useProjectGridData';
import type {PastProjectShare} from '@/features/projects/api';

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

        expect(result.current).toEqual({
            share: null,
            loading: false,
            error: null,
            notFound: false,
            retry: expect.any(Function),
        });
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
        // No HTTP status: the request failed, which says nothing about whether the list exists.
        expect(result.current.notFound).toBe(false);
    });

    it.each([404, 400])('reports a share the API answers %i for as not found', async (status) => {
        mockFetchPastProjectShare.mockRejectedValue(
            Object.assign(new Error(`Request failed with status code ${status}`), {response: {status}}),
        );

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.notFound).toBe(true);
    });

    it.each([500, 502, 503])('does not report a %i as a missing share', async (status) => {
        mockFetchPastProjectShare.mockRejectedValue(
            Object.assign(new Error(`Request failed with status code ${status}`), {response: {status}}),
        );

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe(`Request failed with status code ${status}`);
        expect(result.current.notFound).toBe(false);
    });

    it('loads the share again on retry after a failed request', async () => {
        mockFetchPastProjectShare.mockRejectedValueOnce(new Error('Network Error')).mockResolvedValueOnce(makeShare());

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        await waitFor(() => expect(result.current.error).toBe('Network Error'));

        act(() => result.current.retry());
        expect(result.current.loading).toBe(true);
        expect(result.current.error).toBeNull();

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.share).toMatchObject({id: 'share-1'});
        expect(result.current.error).toBeNull();
        expect(mockFetchPastProjectShare).toHaveBeenCalledTimes(2);
    });

    it('falls back to a generic message for non-Error rejections', async () => {
        mockFetchPastProjectShare.mockRejectedValue('denied');

        const {result} = renderHook(() => usePastProjectShareData('share-1'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('Failed to load shared past projects');
    });
});
