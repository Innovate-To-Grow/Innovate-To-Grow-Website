import {act, renderHook, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {useCMSPage} from '@/features/cms/components/useCMSPage';
import type {CMSPageResponse} from '@/features/cms/api';

const cmsApiMocks = vi.hoisted(() => ({
  fetchCMSLivePreview: vi.fn(),
  fetchCMSPage: vi.fn(),
  fetchCMSPreview: vi.fn(),
}));

vi.mock('@/features/cms/api', () => cmsApiMocks);

const page = (title = 'About I2G'): CMSPageResponse => ({
  slug: 'about',
  route: '/about',
  title,
  page_css_class: 'cms-about',
  page_css: '.cms-about { color: blue; }',
  meta_description: '',
  blocks: [],
});

describe('useCMSPage', () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    window.history.pushState(null, '', '/about');
  });

  it('loads a published CMS page for the requested route', async () => {
    cmsApiMocks.fetchCMSPage.mockResolvedValue(page());

    const {result} = renderHook(() => useCMSPage('/about'));

    expect(result.current).toMatchObject({loading: true, page: null, error: null});
    await waitFor(() => expect(result.current.page?.title).toBe('About I2G'));
    expect(result.current.loading).toBe(false);
    expect(cmsApiMocks.fetchCMSPage).toHaveBeenCalledWith('/about', false);
  });

  it('uses token preview when cms_preview_token is present', async () => {
    window.history.pushState(null, '', '/about?cms_preview_token=preview-token');
    cmsApiMocks.fetchCMSPreview.mockResolvedValue(page('Preview About'));

    const {result} = renderHook(() => useCMSPage('/about', true));

    await waitFor(() => expect(result.current.page?.title).toBe('Preview About'));
    expect(cmsApiMocks.fetchCMSPreview).toHaveBeenCalledWith('preview-token');
    expect(cmsApiMocks.fetchCMSPage).not.toHaveBeenCalled();
  });

  it('reports not_found for 404 responses and error for other failures', async () => {
    cmsApiMocks.fetchCMSPage.mockRejectedValueOnce({response: {status: 404}});
    const missing = renderHook(() => useCMSPage('/missing'));

    await waitFor(() => expect(missing.result.current.error).toBe('not_found'));

    cmsApiMocks.fetchCMSPage.mockRejectedValueOnce(new Error('offline'));
    const failed = renderHook(() => useCMSPage('/offline'));

    await waitFor(() => expect(failed.result.current.error).toBe('error'));
  });

  it('loads and polls live preview content without blanking existing content on transient failures', async () => {
    vi.useFakeTimers();
    window.history.pushState(null, '', '/about?cms_live_preview=42');
    cmsApiMocks.fetchCMSLivePreview
      .mockResolvedValueOnce(page('Live Preview 1'))
      .mockRejectedValueOnce(new Error('transient'))
      .mockResolvedValueOnce(page('Live Preview 2'));

    const {result, unmount} = renderHook(() => useCMSPage('/about'));

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.page?.title).toBe('Live Preview 1');
    expect(result.current.isLivePreview).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(result.current.page?.title).toBe('Live Preview 1');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(result.current.page?.title).toBe('Live Preview 2');

    unmount();
    vi.useRealTimers();
  });
});
