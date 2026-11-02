import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  getPageReloadStatus,
  installPreloadErrorRecovery,
  isChunkLoadError,
  isNewBuildDeployed,
  mayReloadForNewBuild,
  reloadForNewBuild,
  resetPageReloadState,
} from '@/app/pageReload/pageReload';

const originalLocation = window.location;
const NOW = 1_800_000_000_000;

function stubLocation() {
  const reload = vi.fn();
  Object.defineProperty(window, 'location', {configurable: true, value: {reload}});
  return reload;
}

function preloadError(message: string): Event & {payload: Error} {
  return Object.assign(new Event('vite:preloadError', {cancelable: true}), {payload: new Error(message)});
}

/** What Vite's preload helper does with a failed dependency: fire the event, then reject unless it is cancelled. */
async function vitePreload(target: Window, message: string): Promise<'loaded'> {
  const event = preloadError(message);
  target.dispatchEvent(event);
  if (!event.defaultPrevented) throw event.payload;
  return 'loaded';
}

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

  it.each([
    'Failed to fetch dynamically imported module: https://i2g.ucmerced.edu/assets/ProjectDetailPage-CeeAsMfZ.js',
    'error loading dynamically imported module: https://i2g.ucmerced.edu/assets/ProjectDetailPage-CeeAsMfZ.js',
    'Importing a module script failed.',
    'Unable to preload CSS for https://i2g.ucmerced.edu/assets/ProjectDetailPage-B6pqHK5d.css',
  ])('recognises a chunk that failed to load: %s', (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true);
  });

  it('does not take a render error for a chunk error', () => {
    expect(isChunkLoadError(new TypeError("Cannot read properties of undefined (reading 'replace')"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });

  it('reloads the page and remembers that it did', () => {
    const reload = stubLocation();

    expect(mayReloadForNewBuild(NOW)).toBe(true);
    expect(reloadForNewBuild(NOW)).toBe(true);

    expect(getPageReloadStatus()).toBe('reloading');
    expect(reload).toHaveBeenCalledOnce();
    expect(window.sessionStorage.getItem('i2g:reloaded-for-new-build-at')).toBe(String(NOW));
  });

  it('does not reload again right after an automatic reload, so a broken chunk cannot loop', () => {
    const reload = stubLocation();
    expect(reloadForNewBuild(NOW)).toBe(true);
    resetPageReloadState(); // the reloaded page starts afresh, with the same session storage

    expect(mayReloadForNewBuild(NOW + 5_000)).toBe(false);
    expect(reloadForNewBuild(NOW + 5_000)).toBe(false);
    expect(reload).toHaveBeenCalledOnce();

    expect(reloadForNewBuild(NOW + 60_000)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it('does not reload when session storage is unavailable to guard against a loop', () => {
    const reload = stubLocation();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });

    expect(mayReloadForNewBuild(NOW)).toBe(false);
    expect(reloadForNewBuild(NOW)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it('refuses, and says so, when session storage will not keep the stamp', () => {
    const reload = stubLocation();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    expect(mayReloadForNewBuild(NOW)).toBe(true);

    expect(reloadForNewBuild(NOW)).toBe(false);

    expect(reload).not.toHaveBeenCalled();
    expect(getPageReloadStatus()).toBe('refused');
    expect(mayReloadForNewBuild(NOW)).toBe(false);
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

  describe('vite:preloadError', () => {
    it.each([
      'Failed to fetch dynamically imported module: /assets/pdfExport-x.js',
      'Failed to fetch dynamically imported module: /assets/ProjectsPage-x.js',
      'Importing a module script failed.',
    ])('never reloads, and a script that fails still rejects to its caller: %s', async (message) => {
      const reload = stubLocation();
      const target = new EventTarget() as Window;
      const uninstall = installPreloadErrorRecovery(target);

      await expect(vitePreload(target, message)).rejects.toThrow(message);

      expect(reload).not.toHaveBeenCalled();
      expect(getPageReloadStatus()).toBe('idle');
      uninstall();
    });

    it("lets a stylesheet that fails through, so the module's script decides", async () => {
      const reload = stubLocation();
      const target = new EventTarget() as Window;
      const uninstall = installPreloadErrorRecovery(target);

      await expect(vitePreload(target, 'Unable to preload CSS for /assets/ProjectDetailPage-B6pqHK5d.css')).resolves.toBe(
        'loaded',
      );

      expect(reload).not.toHaveBeenCalled();
      uninstall();
    });
  });
});
