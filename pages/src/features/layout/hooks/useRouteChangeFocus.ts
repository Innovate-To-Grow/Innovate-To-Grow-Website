import {useEffect, useRef, type RefObject} from 'react';
import {useLocation} from 'react-router';

/** How long to wait for a page that loads its data first (and its h1 with it). */
const HEADING_WAIT_MS = 10_000;

/** Focus is free to move: the link that started the navigation is gone with the old page. */
const focusIsIdle = (container: HTMLElement): boolean => {
  const active = document.activeElement;
  return !active || active === document.body || active === container || !active.isConnected;
};

/**
 * After a client-side route change, moves focus to the new page's h1 so screen readers announce the page
 * and the next Tab starts from its top (a full page load would do both). The first render is left alone,
 * as are same-page changes (query string, #fragment) and focus the visitor has already placed. A page
 * that renders its h1 only once its data arrives gets focus then.
 */
export function useRouteChangeFocus(containerRef: RefObject<HTMLElement | null>): void {
  const {pathname, hash} = useLocation();
  const previousPathname = useRef(pathname);

  useEffect(() => {
    const container = containerRef.current;
    if (previousPathname.current === pathname || !container || hash) {
      previousPathname.current = pathname;
      return;
    }
    previousPathname.current = pathname;

    const focusHeading = (): boolean => {
      const heading = container.querySelector<HTMLElement>('h1');
      if (!heading) return false;
      if (!focusIsIdle(container)) return true;
      if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
      heading.focus({preventScroll: true});
      return true;
    };
    if (focusHeading()) return;

    const observer = new MutationObserver(() => {
      if (focusHeading()) observer.disconnect();
    });
    observer.observe(container, {childList: true, subtree: true});
    const timeout = window.setTimeout(() => observer.disconnect(), HEADING_WAIT_MS);
    return () => {
      observer.disconnect();
      window.clearTimeout(timeout);
    };
  }, [containerRef, pathname, hash]);
}
