// The CMS live-preview sync (cms-block-editor-parts/live-preview.js) under 429: nothing more is posted until the
// server's wait has passed, then the latest blocks are resent once.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {flush, installPollBackoff, jsonResponse, readRepoFile} from '@/__tests__/core/adminStatic';

const SCRIPT = readRepoFile('src/apps/cms/static/cms/js/cms-block-editor-parts/live-preview.js');
const fetchMock = vi.fn();

interface LivePreview {
  post(blocks: Array<{block_type: string; data: unknown}>, callback?: () => void): void;
  setActive(active: boolean): void;
}

const preview = () => (window as unknown as {ITGCmsBlockLivePreview: LivePreview}).ITGCmsBlockLivePreview;
const sentTitles = () =>
  fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string).blocks[0].data.title);
const block = (title: string) => [{block_type: 'hero', data: {title}}];
const syncText = () => document.getElementById('cms-preview-sync-status')?.textContent;

function open({helper = true} = {}) {
  document.body.innerHTML = `
    <input name="csrfmiddlewaretoken" value="token">
    <div id="cms-inline-preview" class="is-active"><span id="cms-preview-sync-status"></span></div>`;
  (window as unknown as {CMS_ROUTE_EDITOR: unknown}).CMS_ROUTE_EDITOR = {pageId: 'page-1'};
  if (helper) installPollBackoff();
  window.eval(SCRIPT);
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  sessionStorage.clear();
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  delete (window as {I2GPollBackoff?: unknown}).I2GPollBackoff;
  delete (window as {CMS_ROUTE_EDITOR?: unknown}).CMS_ROUTE_EDITOR;
});

describe('CMS live preview under 429', () => {
  it('holds edits during the wait and resends only the latest blocks afterwards', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(429, {retry_after: 3}, {'Retry-After': '3'}));
    fetchMock.mockResolvedValue(jsonResponse(200, {ok: true}));
    open();

    preview().post(block('first'));
    await flush();
    expect(syncText()).toBe('Busy — retrying in 4 seconds');

    preview().post(block('second'));
    preview().post(block('third'));
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(4000);
    expect(sentTitles()).toEqual(['first', 'third']);
    expect(syncText()).toBe('Synced');

    preview().post(block('fourth'));
    await flush();
    expect(sentTitles()).toEqual(['first', 'third', 'fourth']);
  });

  it('replaces a pending resend when refused again, waiting longer', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(429, {}, {'Retry-After': '1'}))
      .mockResolvedValueOnce(jsonResponse(429, {}, {'Retry-After': '1'}))
      .mockResolvedValue(jsonResponse(200, {}));
    open();

    preview().post(block('a'));
    await flush();
    await vi.advanceTimersByTimeAsync(4000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(syncText()).toBe('Busy — retrying in 8 seconds');
    await vi.advanceTimersByTimeAsync(7999);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('drops the resend once the preview is closed', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(429, {}, {'Retry-After': '1'}));
    open();

    preview().post(block('a'));
    await flush();
    document.getElementById('cms-inline-preview')!.classList.remove('is-active');
    await vi.advanceTimersByTimeAsync(5000);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('only warns about a 429 when the helper did not load', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    fetchMock.mockResolvedValue(jsonResponse(429, {}));
    open({helper: false});

    preview().post(block('a'));
    await flush();

    expect(warn).toHaveBeenCalledWith('[CMS Preview] POST failed with status 429');
  });
});
