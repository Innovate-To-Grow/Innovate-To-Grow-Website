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

    it('serves a seed that is the share at the id without requesting it', async () => {
        const seed = makeShare({name: 'Just saved'});

        const {result} = renderHook(() => usePastProjectShareData('share-1', seed));

        expect(result.current).toMatchObject({share: seed, loading: false, error: null, notFound: false});
        await act(async () => {});
        expect(mockFetchPastProjectShare).not.toHaveBeenCalled();
    });

    it('loads the share when the seed is another share', async () => {
        mockFetchPastProjectShare.mockResolvedValue(makeShare());

        const {result} = renderHook(() => usePastProjectShareData('share-1', makeShare({id: 'share-2'})));

        expect(result.current.loading).toBe(true);
        await waitFor(() => expect(result.current.share).toMatchObject({id: 'share-1', name: 'Shared'}));
        expect(mockFetchPastProjectShare).toHaveBeenCalledWith('share-1');
    });

    it('uses a seed once: Try again, or coming back to its id, loads the share from the server', async () => {
        const seed = makeShare({name: 'Just saved'});
        mockFetchPastProjectShare.mockImplementation(async (id: string) => makeShare({id, name: `Loaded ${id}`}));

        const {result, rerender} = renderHook(({shareId}) => usePastProjectShareData(shareId, seed), {
            initialProps: {shareId: 'share-1'},
        });
        expect(result.current.share).toBe(seed);

        act(() => result.current.retry());
        await waitFor(() => expect(result.current.share).toMatchObject({name: 'Loaded share-1'}));
        expect(mockFetchPastProjectShare).toHaveBeenCalledTimes(1);

        rerender({shareId: 'share-2'});
        await waitFor(() => expect(result.current.share).toMatchObject({name: 'Loaded share-2'}));
        rerender({shareId: 'share-1'});
        await waitFor(() => expect(result.current.share).toMatchObject({name: 'Loaded share-1'}));
        expect(mockFetchPastProjectShare).toHaveBeenCalledTimes(3);
    });

    it('lets a seed handed over after mounting stand in for the load in flight', async () => {
        let resolve!: (share: PastProjectShare) => void;
        mockFetchPastProjectShare.mockReturnValue(
            new Promise<PastProjectShare>((res) => {
                resolve = res;
            }),
        );
        const seed = makeShare({name: 'Just saved', version: 2});

        const {result, rerender} = renderHook(({current}) => usePastProjectShareData('share-1', current), {
            initialProps: {current: null as PastProjectShare | null},
        });
        expect(result.current.loading).toBe(true);
        rerender({current: seed});
        expect(result.current.share).toBe(seed);

        // The older answer of the request the seed replaced is not shown over it.
        await act(async () => {
            resolve(makeShare({name: 'Older', version: 1}));
        });
        expect(result.current.share).toBe(seed);
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
