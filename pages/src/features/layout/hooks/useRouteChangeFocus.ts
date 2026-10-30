import {useEffect, useEffectEvent, useRef, type RefObject} from 'react';
import {useLocation, useNavigationType} from 'react-router';

/** How long to wait for a page that loads its data first (and its h1 with it). */
const HEADING_WAIT_MS = 10_000;

/** Input that shows the visitor is using the page: a click (a screen reader's activation sends one alone) or a key. */
const VISITOR_INPUT_EVENTS = ['click', 'keydown'] as const;

/** Focus is free to move: the link that started the navigation is gone with the old page. */
const focusIsIdle = (container: HTMLElement): boolean => {
  const active = document.activeElement;
  return !active || active === document.body || active === container || !active.isConnected;
};

/**
 * After a client-side route change, moves focus to the new page's h1 so screen readers announce the page
 * and the next Tab starts from its top (a full page load would do both). The page the document loaded
 * with is left alone, including where it redirected to before the visitor did anything (a legacy path,
 * a sign-in guard): there the first Tab still belongs to the skip link and the header. Same-page changes
 * (query string, #fragment) and focus the visitor has already placed are left alone too. A page that
 * renders its h1 only once its data arrives gets focus then.
 */
export function useRouteChangeFocus(containerRef: RefObject<HTMLElement | null>): void {
  const {pathname, hash} = useLocation();
  const navigationType = useNavigationType();
  const previousPathname = useRef(pathname);
  // Set by the visitor's first click or key press, or first move to another page (a link, back/forward). A
  // redirect (REPLACE) before it still belongs to the page the document loaded with; one after it is the
  // visitor's own step (a sign-in form that replaces itself with the account page).
  const visitorActed = useRef(false);
  // Read with each pathname change; a later change of type alone (a query string replaced on the same
  // page) must not cancel the wait for the new page's h1.
  const isRedirect = useEffectEvent(() => navigationType === 'REPLACE');

  useEffect(() => {
    const markActed = () => {
      visitorActed.current = true;
      stopListening();
    };
    const stopListening = () => {
      for (const type of VISITOR_INPUT_EVENTS) window.removeEventListener(type, markActed, true);
    };
    for (const type of VISITOR_INPUT_EVENTS) window.addEventListener(type, markActed, true);
    return stopListening;
  }, []);

  useEffect(() => {
    if (previousPathname.current === pathname) return;
    previousPathname.current = pathname;
    if (!isRedirect()) visitorActed.current = true;
    const container = containerRef.current;
    if (!container || hash || !visitorActed.current) return;

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
