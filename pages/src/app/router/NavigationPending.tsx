import './NavigationPending.css';
import {useEffect, useState, useSyncExternalStore} from 'react';
import {useLocation} from 'react-router';
import {reloadPage} from '@/app/pageReload';

/** Long enough that a chunk from cache or a fast network never flashes the bar. */
const PENDING_SHOW_DELAY_MS = 300;
/** After this long the route chunk is probably not coming: offer a reload. */
const PENDING_SLOW_AFTER_MS = 10_000;

/** The part of the data router this indicator reads: its latest location, ahead of what React shows. */
export interface LatestLocationSource {
  subscribe: (listener: () => void) => () => void;
  getLocationKey: () => string;
}

type Phase = 'shown' | 'slow';

interface NavigationPendingProps {
  source: LatestLocationSource;
  showDelayMs?: number;
  slowAfterMs?: number;
}

/**
 * Feedback while a route is still loading its chunk. The router commits navigations in a React
 * transition, so until the new page's lazy chunk arrives React keeps the old page on screen (and
 * skips the route's Suspense fallback): the URL has changed, nothing else has. The router's own
 * location runs ahead of the rendered one (useLocation) for exactly that long; while they differ, a
 * progress bar shows, and if it takes very long, a notice offers to reload the page.
 */
export function NavigationPending({
  source,
  showDelayMs = PENDING_SHOW_DELAY_MS,
  slowAfterMs = PENDING_SLOW_AFTER_MS,
}: NavigationPendingProps) {
  const renderedKey = useLocation().key;
  const latestKey = useSyncExternalStore(source.subscribe, source.getLocationKey);
  const pending = latestKey !== renderedKey;
  const [phase, setPhase] = useState<{key: string; phase: Phase} | null>(null);

  useEffect(() => {
    if (!pending) return;
    const show = window.setTimeout(() => setPhase({key: latestKey, phase: 'shown'}), showDelayMs);
    const slow = window.setTimeout(() => setPhase({key: latestKey, phase: 'slow'}), slowAfterMs);
    return () => {
      window.clearTimeout(show);
      window.clearTimeout(slow);
    };
  }, [pending, latestKey, showDelayMs, slowAfterMs]);

  const current = pending && phase?.key === latestKey ? phase.phase : null;
  return (
    <>
      {current ? <div className="itg-navigation-progress" aria-hidden="true" /> : null}
      <div className="sr-only" role="status">
        {current ? 'Loading page…' : ''}
      </div>
      {current === 'slow' ? (
        <div className="itg-navigation-slow" role="alert">
          <p className="itg-navigation-slow-text">This page is taking longer than usual to load.</p>
          <button type="button" className="itg-btn itg-btn-primary" onClick={reloadPage}>
            Reload page
          </button>
        </div>
      ) : null}
    </>
  );
}
