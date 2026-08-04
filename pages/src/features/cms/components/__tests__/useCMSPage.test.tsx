import {act, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const fetchCMSLivePreview = vi.hoisted(() => vi.fn());
const fetchCMSPage = vi.hoisted(() => vi.fn());
const fetchCMSPreview = vi.hoisted(() => vi.fn());

vi.mock('@/features/cms/api', () => ({
  fetchCMSLivePreview,
  fetchCMSPage,
  fetchCMSPreview,
}));

import {useCMSPage} from '../useCMSPage';

describe('useCMSPage live polling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.history.replaceState(
      {},
      '',
      '/about?cms_live_preview=preview-1',
    );
    fetchCMSLivePreview.mockReset();
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
