import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';
import { trackPageView } from '@/lib/api';
import {isIsolatedRoute} from '@/lib/isolatedRoute';

/** Siteimprove's command queue, present once its script (thirdPartyLoaders) has loaded. */
type SiteimproveWindow = Window & {_sz?: {push: (command: unknown[]) => unknown}};

export function usePageTracking() {
  const location = useLocation();
  const prevPath = useRef<string | null>(null);
  // The last tracked in-app URL: the referrer of the next client-side page view.
  const prevUrl = useRef<string | null>(null);

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

    const track = () => {
      if (isIsolatedRoute(location.pathname, location.search)) return;
      void trackPageView({path: currentPath, referrer: inAppReferrer ?? document.referrer});
      // Siteimprove counts the document load and link clicks only; a client-side route change is a new
      // page view only when announced. Its handler reads location.href and document.title, which the
      // route has set by the time this idle callback runs.
      if (inAppReferrer !== null) (window as SiteimproveWindow)._sz?.push(['trackdynamic']);
    };
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(track, {timeout: 2000});
      return () => window.cancelIdleCallback(id);
    }
    const id = globalThis.setTimeout(track, 1000);
    return () => globalThis.clearTimeout(id);
  }, [location.pathname, location.search]);
}
