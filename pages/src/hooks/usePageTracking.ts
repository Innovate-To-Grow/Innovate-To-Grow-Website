import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from '@/lib/analytics';

export function usePageTracking() {
  const location = useLocation();
  const prevPath = useRef<string | null>(null);

  useEffect(() => {
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

    trackPageView({
      path: currentPath,
      referrer: document.referrer,
    });
  }, [location.pathname, location.search]);
}
