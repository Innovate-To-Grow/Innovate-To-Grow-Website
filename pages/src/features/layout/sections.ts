import type {MenuItem} from '@/features/layout/api';

/**
 * Section resolution for the header menu row (current-section underline and
 * aria-current).
 *
 * A "section" is a top-level CMS menu item. The menu row highlights the
 * top-level item whose own URL is the current page, otherwise the first one
 * that contains the page among its descendants.
 */

export interface SectionMatch {
  /** Index of the top-level menu item to underline in the menu row, or null. */
  menuIndex: number | null;
  /** Normalised path the navigation treats as the current page. */
  currentPath: string;
  /**
   * True when `currentPath` is the page itself. False when a detail route was
   * mapped to its list page (e.g. /projects/:id -> /current-projects), in which
   * case links use aria-current="true" instead of "page".
   */
  isExact: boolean;
}

interface PathCandidate {
  path: string;
  exact: boolean;
}

/** Detail routes and aliases, mapped to the menu page(s) they belong to (first match wins). */
const DETAIL_ROUTE_RULES: ReadonlyArray<readonly [RegExp, readonly string[]]> = [
  [/^\/projects\/[^/]+$/, ['/current-projects']],
  [/^\/past-projects\/project\/[^/]+$/, ['/past-projects']],
  [/^\/past-projects\/[^/]+$/, ['/past-projects']],
  [/^\/news\/[^/]+$/, ['/news']],
  [/^\/events\/[^/]+$/, ['/past-events', '/event', '/events']],
  [/^\/membership\/events$/, ['/event-registration']],
];

export const normalizePath = (path: string): string => {
  const withoutQuery = (typeof path === 'string' ? path : '').split(/[?#]/, 1)[0] ?? '';
  const collapsed = `/${withoutQuery}`.replace(/\/{2,}/g, '/').toLowerCase();
  return collapsed.length > 1 ? collapsed.replace(/\/+$/, '') || '/' : '/';
};

/** Normalised same-origin path of a menu item, or null for off-site / empty URLs. */
export const menuItemPath = (item: Pick<MenuItem, 'url'>): string | null => {
  const url = typeof item.url === 'string' ? item.url.trim() : '';
  if (!url || url.startsWith('#')) return null;
  if (url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/\\')) {
    return normalizePath(url);
  }
  if (!/^https?:\/\//i.test(url) || typeof window === 'undefined') return null;
  try {
    const parsed = new URL(url);
    return parsed.origin === window.location.origin ? normalizePath(parsed.pathname) : null;
  } catch {
    return null;
  }
};

const hasDescendantPath = (items: MenuItem[] | undefined, path: string): boolean =>
  (items ?? []).some((child) => menuItemPath(child) === path || hasDescendantPath(child.children, path));

const candidatePaths = (path: string): PathCandidate[] => {
  const candidates: PathCandidate[] = [{path, exact: true}];
  for (const [pattern, targets] of DETAIL_ROUTE_RULES) {
    if (pattern.test(path)) {
      candidates.push(...targets.map((target) => ({path: target, exact: false})));
      break;
    }
  }
  // Generic fallback: a nested page belongs to its closest ancestor page.
  const segments = path.split('/').filter(Boolean);
  for (let length = segments.length - 1; length > 0; length -= 1) {
    candidates.push({path: `/${segments.slice(0, length).join('/')}`, exact: false});
  }
  return candidates;
};

const findMenuIndex = (items: MenuItem[], path: string): number | null => {
  const own = items.findIndex((item) => menuItemPath(item) === path);
  if (own >= 0) return own;
  const parent = items.findIndex((item) => hasDescendantPath(item.children, path));
  return parent >= 0 ? parent : null;
};

export const resolveSection = (items: MenuItem[] | null | undefined, pathname: string): SectionMatch => {
  const path = normalizePath(pathname);
  const menuItems = items ?? [];
  if (path === '/') {
    return {menuIndex: findMenuIndex(menuItems, '/'), currentPath: '/', isExact: true};
  }
  for (const candidate of candidatePaths(path)) {
    const menuIndex = findMenuIndex(menuItems, candidate.path);
    if (menuIndex === null) continue;
    return {menuIndex, currentPath: candidate.path, isExact: candidate.exact};
  }
  return {menuIndex: null, currentPath: path, isExact: true};
};

/**
 * aria-current value for a link to `itemPath`: "page" for the page itself,
 * "true" when a detail page maps onto this list page, undefined otherwise.
 */
export const ariaCurrentFor = (
  itemPath: string | null,
  match: Pick<SectionMatch, 'currentPath' | 'isExact'>,
): 'page' | 'true' | undefined => {
  if (!itemPath || itemPath !== match.currentPath) return undefined;
  return match.isExact ? 'page' : 'true';
};
