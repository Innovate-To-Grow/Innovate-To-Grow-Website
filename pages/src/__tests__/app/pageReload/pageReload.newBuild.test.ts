import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  isNewBuildDeployed,
  resetPageReloadState,
} from '@/app/pageReload/pageReload';

const originalLocation = window.location;
describe('pageReload', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetPageReloadState();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetPageReloadState();
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', {configurable: true, value: originalLocation});
  });

  describe('isNewBuildDeployed', () => {
    const RUNNING_ENTRY = '/assets/index-OldBuild1.js';
    const pageHtml = (entry: string) =>
      `<!doctype html><html><head><script type="module" crossorigin src="${entry}"></script></head><body></body></html>`;
    const serve = (response: Response) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    beforeEach(() => {
      document.head.innerHTML = `<script type="module" crossorigin src="${RUNNING_ENTRY}"></script>`;
    });

    afterEach(() => {
      vi.useRealTimers();
      vi.unstubAllGlobals();
      document.head.innerHTML = '';
    });

    it("is true when the page's HTML now names another entry script, fetched uncached by path alone", async () => {
      serve(new Response(pageHtml('/assets/index-NewBuild2.js')));

      await expect(isNewBuildDeployed()).resolves.toBe(true);

      expect(fetch).toHaveBeenCalledWith(window.location.pathname, expect.objectContaining({cache: 'no-store'}));
    });

    it('is false while the same build is deployed (a chunk that fails anyway, or loads cancelled by leaving)', async () => {
      serve(new Response(pageHtml(RUNNING_ENTRY)));

      await expect(isNewBuildDeployed()).resolves.toBe(false);
    });

    it('is false when the answer is not a page, or no answer comes', async () => {
      serve(new Response('Not found', {status: 404}));
      await expect(isNewBuildDeployed()).resolves.toBe(false);

      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Load failed')));
      await expect(isNewBuildDeployed()).resolves.toBe(false);
    });

    it('gives up as no after five seconds', async () => {
      vi.useFakeTimers();
      vi.stubGlobal(
        'fetch',
        vi.fn(
          (_url: string, init: RequestInit) =>
            new Promise((_resolve, reject) =>
              init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))),
            ),
        ),
      );

      const answer = isNewBuildDeployed();
      await vi.advanceTimersByTimeAsync(5_000);

      await expect(answer).resolves.toBe(false);
    });

    it('does not ask without an entry script to compare (the dev server)', async () => {
      document.head.innerHTML = '';
      serve(new Response(pageHtml('/assets/index-NewBuild2.js')));

      await expect(isNewBuildDeployed()).resolves.toBe(false);
      expect(fetch).not.toHaveBeenCalled();
    });
  });
});
