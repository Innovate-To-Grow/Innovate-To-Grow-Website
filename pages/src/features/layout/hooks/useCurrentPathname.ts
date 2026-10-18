import {useSyncExternalStore} from 'react';

/**
 * The header (#menu-root) and footer roots render outside the router, so they
 * cannot use useLocation(). The page shell (Container, inside the router)
 * announces every route change with this window event; popstate covers
 * back/forward. Both re-read window.location, which the router has already
 * updated by the time either fires.
 */
export const ROUTE_CHANGE_EVENT = 'i2g-route-change';

export const notifyRouteChange = (pathname: string) => {
  window.dispatchEvent(new CustomEvent(ROUTE_CHANGE_EVENT, {detail: {pathname}}));
};

const subscribe = (onChange: () => void) => {
  window.addEventListener('popstate', onChange);
  window.addEventListener(ROUTE_CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener('popstate', onChange);
    window.removeEventListener(ROUTE_CHANGE_EVENT, onChange);
  };
};

const getPathname = () => window.location?.pathname || '/';
const getServerPathname = () => '/';

export const useCurrentPathname = (): string => useSyncExternalStore(subscribe, getPathname, getServerPathname);
