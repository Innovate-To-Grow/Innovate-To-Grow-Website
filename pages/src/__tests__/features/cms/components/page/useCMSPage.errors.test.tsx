import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const fetchCMSLivePreview = vi.hoisted(() => vi.fn());
const fetchCMSHomepage = vi.hoisted(() => vi.fn());
const fetchCMSPage = vi.hoisted(() => vi.fn());
const fetchCMSPreview = vi.hoisted(() => vi.fn());

vi.mock('@/features/cms/api', () => ({
  fetchCMSLivePreview,
  fetchCMSHomepage,
  fetchCMSPage,
  fetchCMSPreview,
  isCMSPageRedirectResponse: (value: {redirect_to?: unknown; permanent?: unknown}) => (
    typeof value?.redirect_to === 'string' && value.permanent === true
  ),
}));

import {useCMSPage} from '@/features/cms/components/page/useCMSPage';

describe('useCMSPage errors, retry, and cleanup', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/old');
    fetchCMSLivePreview.mockReset();
    fetchCMSHomepage.mockReset();
    fetchCMSPage.mockReset();
    fetchCMSPreview.mockReset();
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState({}, '', '/');
  });

  it('maps a 404 response to a not_found error', async () => {
    fetchCMSPage.mockRejectedValue({response: {status: 404}});

    const {result} = renderHook(() => useCMSPage('/old'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('not_found');
    expect(result.current.page).toBeNull();
  });

  it('maps a non-404 failure to a generic error', async () => {
    fetchCMSPage.mockRejectedValue({response: {status: 500}});

    const {result} = renderHook(() => useCMSPage('/old'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('error');
  });

  it('re-fetches when retry is called', async () => {
    fetchCMSPage.mockRejectedValue({response: {status: 500}});
    const {result} = renderHook(() => useCMSPage('/old'));

    await waitFor(() => expect(result.current.error).toBe('error'));

    fetchCMSPage.mockResolvedValue({route: '/old', blocks: []});
    act(() => {
      result.current.retry();
    });

    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.page).toEqual({route: '/old', blocks: []});
    expect(fetchCMSPage).toHaveBeenCalledTimes(2);
  });

  it('ignores a response that arrives after unmount', async () => {
    let resolve!: (value: {route: string; blocks: unknown[]}) => void;
    fetchCMSPage.mockReturnValue(
      new Promise((next) => {
        resolve = next;
      }),
    );

    const {unmount} = renderHook(() => useCMSPage('/old'));
    unmount();

    await act(async () => {
      resolve({route: '/old', blocks: []});
      await Promise.resolve();
    });
  });

  it('ignores a rejection that arrives after unmount', async () => {
    let reject!: (reason: unknown) => void;
    fetchCMSPage.mockReturnValue(
      new Promise((_next, rejectFn) => {
        reject = rejectFn;
      }),
    );

    const {unmount} = renderHook(() => useCMSPage('/old'));
    unmount();

    await act(async () => {
      reject({response: {status: 500}});
      await Promise.resolve();
    });
  });

  it('exposes a working retry during the initial loading state', async () => {
    fetchCMSPage.mockResolvedValue({route: '/old', blocks: []});

    const {result} = renderHook(() => useCMSPage('/old'));

    expect(result.current.loading).toBe(true);
    act(() => {
      result.current.retry();
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchCMSPage).toHaveBeenCalledTimes(2);
  });
});
