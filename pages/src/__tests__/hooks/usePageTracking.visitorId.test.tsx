import {cleanup, renderHook, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import type {ReactNode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
}));

// Only the HTTP client is mocked: the hook runs against the real trackPageView.
vi.mock('@/lib/api/api-client', () => ({
  api: {post: mocks.post, get: vi.fn()},
}));

import {usePageTracking} from '@/hooks/usePageTracking';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function wrapperFor(initialEntry: string) {
  return function RouterWrapper({children}: {children: ReactNode}) {
    return <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>;
  };
}

describe('usePageTracking visitor id', () => {
  beforeEach(() => {
    mocks.post.mockReset();
    mocks.post.mockResolvedValue({status: 201});
    window.localStorage.clear();
    window.requestIdleCallback = ((callback: (deadline: IdleDeadline) => void) => {
      callback({didTimeout: false, timeRemaining: () => 50});
      return 1;
    }) as unknown as Window['requestIdleCallback'];
    window.cancelIdleCallback = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
    delete (window as {requestIdleCallback?: unknown}).requestIdleCallback;
    delete (window as {cancelIdleCallback?: unknown}).cancelIdleCallback;
  });

  it('sends the same stored visitor id with the page views of separate page loads', async () => {
    renderHook(() => usePageTracking(), {wrapper: wrapperFor('/about')});
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
    cleanup();
    renderHook(() => usePageTracking(), {wrapper: wrapperFor('/projects')});
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));

    const [first, second] = mocks.post.mock.calls;
    expect(first[0]).toBe('/analytics/pageview/');
    expect(first[1]).toEqual({path: '/about', referrer: document.referrer, visitor_id: expect.stringMatching(UUID_V4)});
    expect(second[1]).toEqual({path: '/projects', referrer: document.referrer, visitor_id: first[1].visitor_id});
    expect(window.localStorage.getItem('i2g_visitor_id')).toBe(first[1].visitor_id);
  });

  it('still tracks the page view when localStorage is blocked', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });

    renderHook(() => usePageTracking(), {wrapper: wrapperFor('/about')});

    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
    expect(mocks.post.mock.calls[0][1]).toEqual({
      path: '/about',
      referrer: document.referrer,
      visitor_id: expect.stringMatching(UUID_V4),
    });
  });
});
