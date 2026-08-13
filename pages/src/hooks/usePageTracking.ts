import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';
import { trackPageView } from '@/lib/api';
import {isIsolatedRoute} from '@/lib/isolatedRoute';

export function usePageTracking() {
  const location = useLocation();
  const prevPath = useRef<string | null>(null);

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

    const track = () => {
      if (isIsolatedRoute(location.pathname, location.search)) return;
      void trackPageView({path: currentPath, referrer: document.referrer});
    };
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(track, {timeout: 2000});
      return () => window.cancelIdleCallback(id);
    }
    const id = globalThis.setTimeout(track, 1000);
    return () => globalThis.clearTimeout(id);
  }, [location.pathname, location.search]);
}
