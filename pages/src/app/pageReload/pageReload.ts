/**
 * Full-page reloads that recover from a stale build.
 *
 * Every frontend deploy replaces the hashed /assets/* files, so a tab opened before it fails the first
 * time it needs a route chunk it has not loaded yet. The only way back is a full reload, which fetches
 * the new index.html and its new chunk names. It happens once on its own; if the chunk still fails
 * right after, the route error screen offers the reload instead of looping.
 */

const RELOAD_STAMP_KEY = 'i2g:reloaded-for-new-build-at';
/** A second failure this soon after an automatic reload is not a stale build: stop and ask instead. */
const RELOAD_LOOP_WINDOW_MS = 30_000;

// Browsers word a failed dynamic import differently; Vite adds its own for a failed stylesheet.
const CHUNK_ERROR_PATTERNS = [
  /Failed to fetch dynamically imported module/i, // Chromium
  /error loading dynamically imported module/i, // Firefox
  /Importing a module script failed/i, // WebKit
  /Unable to preload CSS/i, // Vite's preload helper
];

let reloading = false;
const reloadListeners = new Set<() => void>();

const messageOf = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  return typeof error === 'string' ? error : '';
};

/** Whether `error` is a route chunk (script or stylesheet) that failed to load. */
export function isChunkLoadError(error: unknown): boolean {
  const message = messageOf(error);
  return CHUNK_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

/** Whether a reload has been started, so error screens can say so instead of flashing. */
export function isReloadingPage(): boolean {
  return reloading;
}

/** Subscribes to the start of a reload (a `useSyncExternalStore` source with `isReloadingPage`). */
export function subscribeToPageReload(listener: () => void): () => void {
  reloadListeners.add(listener);
  return () => {
    reloadListeners.delete(listener);
  };
}

/** Reloads the page (index.html is served with max-age=0, so it comes back revalidated). */
export function reloadPage(): void {
  reloading = true;
  reloadListeners.forEach((listener) => listener());
  window.location.reload();
}

/**
 * Reloads once to pick up a new build. Returns false, without reloading, when the last automatic reload
 * was moments ago (the failure is not a stale build, so a reload would loop) or when session storage is
 * unavailable to remember it.
 */
export function reloadForNewBuild(now = Date.now()): boolean {
  if (reloading) return true;
  try {
    const last = Number(window.sessionStorage.getItem(RELOAD_STAMP_KEY));
    if (last && now - last < RELOAD_LOOP_WINDOW_MS) return false;
    window.sessionStorage.setItem(RELOAD_STAMP_KEY, String(now));
  } catch {
    return false;
  }
  reloadPage();
  return true;
}

interface VitePreloadErrorEvent extends Event {
  payload?: unknown;
}

/**
 * Vite's preload helper fires `vite:preloadError` (cancelable) before a route chunk's import rejects.
 * The first failure reloads onto the new build. If that already happened, a stylesheet that still fails
 * is let through, so the page renders without it rather than not at all; a script failure goes on to
 * the route error screen.
 */
export function installPreloadErrorRecovery(target: Window = window): () => void {
  const onPreloadError = (event: Event) => {
    if (reloadForNewBuild()) return;
    if (/Unable to preload CSS/i.test(messageOf((event as VitePreloadErrorEvent).payload))) event.preventDefault();
  };
  target.addEventListener('vite:preloadError', onPreloadError);
  return () => target.removeEventListener('vite:preloadError', onPreloadError);
}

/** Test hook: forget that a reload was started. */
export function resetPageReloadState(): void {
  reloading = false;
}
