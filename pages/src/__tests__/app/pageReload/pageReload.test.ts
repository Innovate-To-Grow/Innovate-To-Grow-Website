import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  getPageReloadStatus,
  installPreloadErrorRecovery,
  isChunkLoadError,
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

  describe('vite:preloadError', () => {
    it.each([
      'Failed to fetch dynamically imported module: /assets/pdfExport-x.js',
      'Failed to fetch dynamically imported module: /assets/ProjectsPage-x.js',
      'Unable to preload CSS for /assets/ProjectDetailPage-B6pqHK5d.css',
    ])('never reloads, and the import still rejects to its caller: %s', async (message) => {
      const reload = stubLocation();
      const target = new EventTarget() as Window;
      const uninstall = installPreloadErrorRecovery(target);

      await expect(vitePreload(target, message)).rejects.toThrow(message);

      expect(reload).not.toHaveBeenCalled();
      expect(getPageReloadStatus()).toBe('idle');
      uninstall();
    });

    it('right after an automatic reload, lets a stylesheet that still fails through, but not a script', async () => {
      stubLocation();
      window.sessionStorage.setItem('i2g:reloaded-for-new-build-at', String(Date.now()));
      const target = new EventTarget() as Window;
      const uninstall = installPreloadErrorRecovery(target);
      const script = 'Failed to fetch dynamically imported module: /assets/ProjectDetailPage-C.js';

      await expect(vitePreload(target, 'Unable to preload CSS for /assets/ProjectDetailPage-B6pqHK5d.css')).resolves.toBe(
        'loaded',
      );
      await expect(vitePreload(target, script)).rejects.toThrow(script);
      uninstall();
    });
  });
});
