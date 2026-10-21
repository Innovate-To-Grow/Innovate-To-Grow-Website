import {useEffect, useRef, useState} from 'react';
import {clearCMSRouteRedirectChain, performCMSRouteRedirect} from '../cmsRouteRedirect';

export type RedirectFailure = 'not_found' | 'error';

/**
 * Follow a CMS page's `redirect_to` (never while previewing). Each route + target pair is attempted once;
 * a failed attempt (invalid target, loop, or a thrown navigation) is returned so the page can show it.
 * A page that loads without a redirect ends the tab-scoped redirect chain, so a later, independent visit
 * to the same legacy URL may start a fresh redirect.
 */
export function useCMSRouteRedirect(
  route: string,
  redirectTo: string | null | undefined,
  {previewing, page}: {previewing: boolean; page: object | null},
): RedirectFailure | null {
  const [redirectFailure, setRedirectFailure] = useState<{key: string; kind: RedirectFailure} | null>(null);
  const redirectAttemptRef = useRef<{key: string; failure: RedirectFailure | null} | null>(null);
  const redirectKey = redirectTo ? `${route}\n${redirectTo}` : null;

  useEffect(() => {
    if (!redirectTo || !redirectKey || previewing) {
      return;
    }

    let cancelled = false;
    const publishFailure = (kind: RedirectFailure) => {
      queueMicrotask(() => {
        if (!cancelled) {
          setRedirectFailure({key: redirectKey, kind});
        }
      });
    };

    const previousAttempt = redirectAttemptRef.current;
    if (previousAttempt?.key === redirectKey) {
      if (previousAttempt.failure) {
        publishFailure(previousAttempt.failure);
      }
    } else {
      try {
        const result = performCMSRouteRedirect(redirectTo);
        const failure = result === 'redirected' ? null : 'not_found';
        redirectAttemptRef.current = {key: redirectKey, failure};
        if (failure) publishFailure(failure);
      } catch {
        redirectAttemptRef.current = {key: redirectKey, failure: 'error'};
        publishFailure('error');
      }
    }

    return () => {
      cancelled = true;
    };
  }, [redirectTo, redirectKey, previewing]);

  useEffect(() => {
    if (page && !redirectTo && !previewing) {
      clearCMSRouteRedirectChain();
    }
  }, [page, redirectTo, previewing]);

  return redirectFailure?.key === redirectKey ? redirectFailure.kind : null;
}
