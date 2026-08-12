/**
 * Encodes the rule for hiding the assistant widget on iframe-isolated routes.
 *
 * Mirrors the `isBlockPreview` guard in `app/providers.tsx`: the widget is
 * suppressed on the admin block-preview route, public embed routes, and any URL
 * carrying the `_isolated` flag.
 *
 * @param pathname - `window.location.pathname`
 * @param search   - `window.location.search`
 * @returns `false` when the widget must NOT mount, `true` otherwise.
 */
export function shouldMountWidget(pathname: string, search: string): boolean {
  const isolated = new URLSearchParams(search).has('_isolated');
  const isBlockPreview = pathname === '/_block-preview' || pathname.startsWith('/_embed/') || isolated;
  return !isBlockPreview;
}
