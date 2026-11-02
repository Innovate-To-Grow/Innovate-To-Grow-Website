import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';
import { trackPageView } from '@/lib/api';
import {isIsolatedRoute} from '@/lib/isolatedRoute';

/** Siteimprove's command queue, present once its script (thirdPartyLoaders) has loaded. */
type SiteimproveWindow = Window & {_sz?: {push: (command: unknown[]) => unknown}};

/** How long a client-side page view waits for its page to name itself from its data (a project). */
const TITLE_WAIT_MS = 5000;

/**
 * Announces a client-side page view to Siteimprove, which counts only the document load and link clicks.
 * It records the tab title, and a page that names itself from its data sets that title only once its
 * request is back: until the title moves off `leftTitle` (the one the previous page was left with), or
 * for at most TITLE_WAIT_MS, the view waits. The returned function sends it at once, for a visitor who
 * moves on first, and does nothing once it has gone.
 */
function announceToSiteimprove(url: string, leftTitle: string): () => void {
  // With the URL: by the time a visitor who moved on is sent, the address bar shows the next page.
  const push = () => (window as SiteimproveWindow)._sz?.push(['trackdynamic', {url, title: document.title}]);
  if (document.title !== leftTitle) {
    push();
    return () => {};
  }
  let pending = true;
  const send = () => {
    if (!pending) return;
    pending = false;
    observer.disconnect();
    window.clearTimeout(timeout);
    push();
  };
  const observer = new MutationObserver(() => {
    if (document.title !== leftTitle) send();
  });
  observer.observe(document.head, {childList: true, subtree: true, characterData: true});
  const timeout = window.setTimeout(send, TITLE_WAIT_MS);
  return send;
}

export function usePageTracking() {
  const location = useLocation();
  const prevPath = useRef<string | null>(null);
  // The last tracked in-app URL: the referrer of the next client-side page view.
  const prevUrl = useRef<string | null>(null);
  // The tab title the previous page was left with. Every effect cleanup runs before the new route's
  // effects, so this still reads the old page's title.
  const leftTitle = useRef('');

  useEffect(
    () => () => {
      leftTitle.current = document.title;
    },
    [location.pathname, location.search],
  );

  useEffect(() => {
    if (isIsolatedRoute(location.pathname, location.search)) return;
    // Event registration identity lives in the ?event= query param; include just that param
    // (only on this route) so per-event traffic stays attributable without tracking arbitrary
    // query strings on other pages.
    const eventSlug =
      location.pathname === '/event-registration' ? new URLSearchParams(location.search).get('event') : null;
    const currentPath = eventSlug
      ? `${location.pathname}?event=${encodeURIComponent(eventSlug)}`
      : location.pathname;

    // Avoid duplicate tracking for the same path
    if (currentPath === prevPath.current) return;
    prevPath.current = currentPath;
    // document.referrer is the page the visit came from and never changes on client-side navigation,
    // so only the first view uses it; later views were referred by the previous in-app page.
    const inAppReferrer = prevUrl.current;
    prevUrl.current = `${window.location.origin}${currentPath}`;
    const titleBefore = leftTitle.current;
    let sendToSiteimprove: (() => void) | undefined;

    const track = () => {
      if (isIsolatedRoute(location.pathname, location.search)) return;
      void trackPageView({path: currentPath, referrer: inAppReferrer ?? document.referrer});
      // Siteimprove counts the first view itself (the document load).
      if (inAppReferrer !== null) {
        sendToSiteimprove = announceToSiteimprove(
          `${window.location.origin}${location.pathname}${location.search}`,
          titleBefore,
        );
      }
    };
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(track, {timeout: 2000});
      return () => {
        window.cancelIdleCallback(id);
        sendToSiteimprove?.();
      };
    }
    const id = globalThis.setTimeout(track, 1000);
    return () => {
      globalThis.clearTimeout(id);
      sendToSiteimprove?.();
    };
  }, [location.pathname, location.search]);
}
