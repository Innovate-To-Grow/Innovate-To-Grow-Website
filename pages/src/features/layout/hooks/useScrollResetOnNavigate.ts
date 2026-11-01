import {useLayoutEffect, useRef} from 'react';
import {useLocation, useNavigationType} from 'react-router';

/**
 * Starts a page reached by a link (or a redirect) at its top, as a full page load would. Without it the
 * window keeps the previous page's scroll position: the bottom "Back to Current Projects" link on a long
 * project page opened the list halfway down. Back/forward (POP) keep the browser's own restoration, and
 * changes within one page (query string, #fragment) do not scroll.
 */
export function useScrollResetOnNavigate(): void {
  const {pathname, hash} = useLocation();
  const navigationType = useNavigationType();
  const previousPathname = useRef(pathname);

  // Before paint, so the new page never shows for a frame at the old position.
  useLayoutEffect(() => {
    if (previousPathname.current === pathname) return;
    previousPathname.current = pathname;
    if (navigationType === 'POP' || hash) return;
    window.scrollTo(0, 0);
  }, [pathname, hash, navigationType]);
}
