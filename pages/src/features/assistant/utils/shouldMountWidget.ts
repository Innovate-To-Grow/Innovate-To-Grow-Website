import {isIsolatedRoute} from '@/lib/isolatedRoute';

/**
 * Encodes the rule for hiding the assistant widget on iframe-isolated routes.
 *
 * The same rule as `isIsolatedRoute` (`app/providers.tsx` also skips the menu
 * and footer roots on it): the widget is suppressed on the admin preview routes,
 * public embed routes, and any URL carrying the `_isolated` flag.
 *
 * @param pathname - `window.location.pathname`
 * @param search   - `window.location.search`
 * @returns `false` when the widget must NOT mount, `true` otherwise.
 */
export function shouldMountWidget(pathname: string, search: string): boolean {
  return !isIsolatedRoute(pathname, search);
}
