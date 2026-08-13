import {act, renderHook, waitFor} from '@testing-library/react';
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

import {useCMSPage} from '@/features/cms/components/useCMSPage';

describe('useCMSPage live polling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.history.replaceState(
      {},
      '',
      '/about?cms_live_preview=preview-1',
    );
    fetchCMSLivePreview.mockReset();
    fetchCMSHomepage.mockReset();
    fetchCMSPage.mockReset();
    fetchCMSPreview.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    window.history.replaceState({}, '', '/');
  });

  it('waits for each live-preview request before scheduling the next', async () => {
    let resolveFirst!: (value: {route: string; blocks: unknown[]}) => void;
    fetchCMSLivePreview
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValue({route: '/about', blocks: []});

    const {unmount} = renderHook(() => useCMSPage('/about'));
    expect(fetchCMSLivePreview).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetchCMSLivePreview).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst({route: '/about', blocks: []});
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(fetchCMSLivePreview).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1499);
    });
    expect(fetchCMSLivePreview).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(fetchCMSLivePreview).toHaveBeenCalledTimes(2);
    unmount();
  });
});

describe('useCMSPage redirects', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/old');
    fetchCMSLivePreview.mockReset();
    fetchCMSHomepage.mockReset();
    fetchCMSPage.mockReset();
    fetchCMSPreview.mockReset();
  });

  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('exposes a permanent redirect response without treating it as a page', async () => {
    fetchCMSPage.mockResolvedValue({
      redirect_to: '/new',
      permanent: true,
    });

    const {result} = renderHook(() => useCMSPage('/old'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current).toMatchObject({
      page: null,
      redirectTo: '/new',
      error: null,
      isLivePreview: false,
    });
  });

  it('does not expose redirects while CMS preview mode is active', async () => {
    window.history.replaceState({}, '', '/old?cms_preview=1');
    fetchCMSPage.mockResolvedValue({
      redirect_to: '/new',
      permanent: true,
    });

    const {result} = renderHook(() => useCMSPage('/old', true));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.redirectTo).toBeNull();
    expect(result.current.error).toBe('error');
  });

  it('keeps token preview responses on the preview fetch path', async () => {
    window.history.replaceState({}, '', '/old?cms_preview_token=opaque-token');
    fetchCMSPreview.mockResolvedValue({route: '/old', blocks: []});

    const {result} = renderHook(() => useCMSPage('/old'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchCMSPreview).toHaveBeenCalledWith('opaque-token');
    expect(fetchCMSPage).not.toHaveBeenCalled();
    expect(result.current.redirectTo).toBeNull();
  });

  it('starts the homepage request directly without a normal CMS page fetch', async () => {
    window.history.replaceState({}, '', '/');
    fetchCMSHomepage.mockResolvedValue({route: '/', blocks: []});

    const {result} = renderHook(() => useCMSPage('/'));

    expect(fetchCMSHomepage).toHaveBeenCalledWith(expect.any(AbortSignal));
    expect(fetchCMSPage).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.loading).toBe(false));
  });
});
