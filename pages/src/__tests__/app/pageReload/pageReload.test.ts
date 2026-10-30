import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  installPreloadErrorRecovery,
  isChunkLoadError,
  isReloadingPage,
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

    expect(reloadForNewBuild(NOW)).toBe(true);

    expect(isReloadingPage()).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
    expect(window.sessionStorage.getItem('i2g:reloaded-for-new-build-at')).toBe(String(NOW));
  });

  it('does not reload again right after an automatic reload, so a broken chunk cannot loop', () => {
    const reload = stubLocation();
    expect(reloadForNewBuild(NOW)).toBe(true);
    resetPageReloadState(); // the reloaded page starts afresh, with the same session storage

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

    expect(reloadForNewBuild(NOW)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  describe('vite:preloadError', () => {
    it('reloads onto the new build on the first failed chunk', () => {
      const reload = stubLocation();
      const target = new EventTarget() as Window;
      const uninstall = installPreloadErrorRecovery(target);
      const event = preloadError('Failed to fetch dynamically imported module: /assets/ProjectsPage-x.js');

      target.dispatchEvent(event);

      expect(reload).toHaveBeenCalledOnce();
      uninstall();
    });

    it('after that, lets the page render without a stylesheet that still fails, but not without a script', () => {
      stubLocation();
      window.sessionStorage.setItem('i2g:reloaded-for-new-build-at', String(Date.now()));
      const target = new EventTarget() as Window;
      const uninstall = installPreloadErrorRecovery(target);
      const cssEvent = preloadError('Unable to preload CSS for /assets/ProjectDetailPage-B6pqHK5d.css');
      const scriptEvent = preloadError('Failed to fetch dynamically imported module: /assets/ProjectDetailPage-C.js');

      target.dispatchEvent(cssEvent);
      target.dispatchEvent(scriptEvent);

      expect(cssEvent.defaultPrevented).toBe(true);
      expect(scriptEvent.defaultPrevented).toBe(false);
      uninstall();
    });
  });
});
