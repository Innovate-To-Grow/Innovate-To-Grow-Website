/**
 * Full-page reloads that recover from a stale build.
 *
 * Every frontend deploy replaces the hashed /assets/* files, so a tab opened before it fails the first
 * time it needs a route chunk it has not loaded yet. The only way back is a full reload, which fetches
 * the new index.html and its new chunk names. The route error screen (RouteErrorPage) starts it once on
 * its own, after checking that another build is deployed: a chunk can also fail while the same build is
 * live (a missing file, a dropped connection, or Safari cancelling the page's loads because the visitor
 * is leaving it), and a reload would not help there, or would cancel the visitor's navigation. If the
 * chunk still fails right after a reload, the screen offers one instead of looping. Other lazy imports
 * (the exporters, the captcha, the chat's Markdown) keep their own error handling: reloading under them
 * would throw away what the visitor was doing.
 */

const RELOAD_STAMP_KEY = 'i2g:reloaded-for-new-build-at';
/** A second failure this soon after an automatic reload is not a stale build: stop and ask instead. */
const RELOAD_LOOP_WINDOW_MS = 30_000;
/** How long the check for a new build may take before it counts as "no" (the error then shows). */
const BUILD_CHECK_TIMEOUT_MS = 5_000;
/** The build's entry script: its file name carries a content hash, so a new build names another one. */
const ENTRY_SCRIPT_SELECTOR = 'script[type="module"][src]';

// Browsers word a failed dynamic import differently; Vite adds its own for a failed stylesheet.
const CHUNK_ERROR_PATTERNS = [
  /Failed to fetch dynamically imported module/i, // Chromium
  /error loading dynamically imported module/i, // Firefox
  /Importing a module script failed/i, // WebKit
  /Unable to preload CSS/i, // Vite's preload helper
];

/**
 * Whether a reload has started, or an automatic one was refused because session storage would not
 * remember it (without that stamp nothing stops a loop).
 */
export type PageReloadStatus = 'idle' | 'reloading' | 'refused';

let status: PageReloadStatus = 'idle';
const reloadListeners = new Set<() => void>();

const setStatus = (next: PageReloadStatus) => {
  status = next;
  reloadListeners.forEach((listener) => listener());
};

const messageOf = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  return typeof error === 'string' ? error : '';
};

/** Whether `error` is a route chunk (script or stylesheet) that failed to load. */
export function isChunkLoadError(error: unknown): boolean {
  const message = messageOf(error);
  return CHUNK_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

/** The reload status, so error screens can say a reload is coming instead of flashing. */
export function getPageReloadStatus(): PageReloadStatus {
  return status;
}

/** Subscribes to status changes (a `useSyncExternalStore` source with `getPageReloadStatus`). */
export function subscribeToPageReload(listener: () => void): () => void {
  reloadListeners.add(listener);
  return () => {
    reloadListeners.delete(listener);
  };
}

/** Reloads the page (index.html is served with max-age=0, so it comes back revalidated). */
export function reloadPage(): void {
  setStatus('reloading');
  window.location.reload();
}

/** When the last automatic reload started: 0 for none, null when session storage is unavailable. */
function lastAutomaticReload(): number | null {
  try {
    return Number(window.sessionStorage.getItem(RELOAD_STAMP_KEY)) || 0;
  } catch {
    return null;
  }
}

/** Whether an automatic reload started moments ago, so a failure now is not a stale build. */
function reloadedMomentsAgo(now: number): boolean {
  const last = lastAutomaticReload();
  return last ? now - last < RELOAD_LOOP_WINDOW_MS : false;
}

/**
 * Whether reloadForNewBuild would reload: there was no automatic reload moments ago (the failure would
 * not be a stale build, so a reload would loop) and session storage is there to remember this one.
 */
export function mayReloadForNewBuild(now = Date.now()): boolean {
  if (status !== 'idle') return status === 'reloading';
  return lastAutomaticReload() !== null && !reloadedMomentsAgo(now);
}

/**
 * Whether a reload would load another build than the running one: fetches this page's HTML again,
 * uncached, and compares its entry script with this document's. Anything short of a clear answer (no
 * entry script, an error, a slow or cancelled request) counts as no.
 */
export async function isNewBuildDeployed(): Promise<boolean> {
  const running = document.querySelector(ENTRY_SCRIPT_SELECTOR)?.getAttribute('src');
  if (!running) return false;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), BUILD_CHECK_TIMEOUT_MS);
  try {
    // The path only: a query string can carry a one-time token (sign-in links) that must not be resent.
    const response = await fetch(window.location.pathname, {cache: 'no-store', signal: controller.signal});
    if (!response.ok) return false;
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    const deployed = html.querySelector(ENTRY_SCRIPT_SELECTOR)?.getAttribute('src');
    return Boolean(deployed) && deployed !== running;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

/** Reloads once to pick up a new build. Returns false, without reloading, when mayReloadForNewBuild is false. */
export function reloadForNewBuild(now = Date.now()): boolean {
  if (status === 'reloading') return true;
  if (!mayReloadForNewBuild(now)) return false;
  try {
    window.sessionStorage.setItem(RELOAD_STAMP_KEY, String(now));
  } catch {
    setStatus('refused');
    return false;
  }
  reloadPage();
  return true;
}

interface VitePreloadErrorEvent extends Event {
  payload?: unknown;
}

/**
 * Vite's preload helper fires `vite:preloadError` (cancelable) before any lazy import rejects; unless
 * the event is cancelled, the import rejects to its caller. This listener never reloads: a route's
 * failure reaches RouteErrorPage, which does when a new build is out, while the other lazy imports
 * report their own errors. A stylesheet that fails is let through, so the module's script decides: if
 * it loads, the page renders without that stylesheet rather than not at all; after a deploy it fails
 * too and the route error screen reloads.
 */
export function installPreloadErrorRecovery(target: Window = window): () => void {
  const onPreloadError = (event: Event) => {
    if (/Unable to preload CSS/i.test(messageOf((event as VitePreloadErrorEvent).payload))) event.preventDefault();
  };
  target.addEventListener('vite:preloadError', onPreloadError);
  return () => target.removeEventListener('vite:preloadError', onPreloadError);
}

/** Test hook: forget that a reload was started or refused. */
export function resetPageReloadState(): void {
  status = 'idle';
}
