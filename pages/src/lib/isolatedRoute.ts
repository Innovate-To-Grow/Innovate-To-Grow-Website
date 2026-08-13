export function isIsolatedRoute(
  pathname = window.location.pathname,
  search = window.location.search,
): boolean {
  return (
    pathname === '/_block-preview' ||
    pathname.startsWith('/_embed/') ||
    new URLSearchParams(search).has('_isolated')
  );
}
