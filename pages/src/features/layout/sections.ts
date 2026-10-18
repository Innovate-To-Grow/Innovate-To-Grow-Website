import type {MenuItem} from '@/features/layout/api';
import {isIsolatedRoute} from '@/lib/isolatedRoute';

/**
 * Section resolution shared by the header menu row (current-section underline)
 * and the page shell (sidebar section nav + phone "In <Section>" select).
 *
 * A "section" is a top-level CMS menu item. The menu row highlights the
 * top-level item whose own URL is the current page, otherwise the first one
 * that contains the page among its descendants. The sidebar only uses
 * top-level items that have children, so a childless top-level duplicate
 * (e.g. "Project Submission") never hides the section it also belongs to.
 */

export interface SectionMatch {
  /** Index of the top-level menu item to underline in the menu row, or null. */
  menuIndex: number | null;
  /** Top-level item with children that the page belongs to, or null (no sidebar). */
  section: MenuItem | null;
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

/** Pages that never show the section nav (auth + account flows). */
const NO_SECTION_NAV_PATHS = [
  '/login',
  '/register',
  '/forgot-password',
  '/verify-email',
  '/verify-phone',
  '/complete-profile',
  '/account',
  '/profile',
  '/login-link',
  '/email-auth-link',
  '/impersonate-login',
  '/magic-login',
  '/ticket-login',
  '/unsubscribe-login',
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

const hasChildren = (item: MenuItem) => Array.isArray(item.children) && item.children.length > 0;

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

const findSection = (items: MenuItem[], path: string): MenuItem | null => {
  const withChildren = items.filter(hasChildren);
  return (
    withChildren.find((item) => menuItemPath(item) === path) ??
    withChildren.find((item) => hasDescendantPath(item.children, path)) ??
    null
  );
};

export const resolveSection = (items: MenuItem[] | null | undefined, pathname: string): SectionMatch => {
  const path = normalizePath(pathname);
  const menuItems = items ?? [];
  if (path === '/') {
    return {menuIndex: findMenuIndex(menuItems, '/'), section: null, currentPath: '/', isExact: true};
  }
  for (const candidate of candidatePaths(path)) {
    const menuIndex = findMenuIndex(menuItems, candidate.path);
    if (menuIndex === null) continue;
    return {
      menuIndex,
      section: findSection(menuItems, candidate.path),
      currentPath: candidate.path,
      isExact: candidate.exact,
    };
  }
  return {menuIndex: null, section: null, currentPath: path, isExact: true};
};

/** Whether the page shell may show the sidebar / section select on this route. */
export const allowsSectionNav = (pathname: string, search = ''): boolean => {
  const path = normalizePath(pathname);
  if (path === '/' || isIsolatedRoute(pathname, search)) return false;
  return !NO_SECTION_NAV_PATHS.some((blocked) => path === blocked || path.startsWith(`${blocked}/`));
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

export interface SectionOption {
  item: MenuItem;
  label: string;
  path: string | null;
}

/** The section landing page (when it is not already one of its children), then every child, depth-first. */
export const sectionOptions = (section: MenuItem): SectionOption[] => {
  const options: SectionOption[] = [];
  const visit = (items: MenuItem[], depth: number) => {
    for (const item of items) {
      options.push({item, label: `${'– '.repeat(depth)}${item.title}`, path: menuItemPath(item)});
      if (item.children?.length) visit(item.children, depth + 1);
    }
  };
  const sectionPath = menuItemPath(section);
  const isListedAsChild = sectionPath !== null && section.children.some((child) => menuItemPath(child) === sectionPath);
  if (section.url && !isListedAsChild) {
    options.push({item: section, label: section.title, path: sectionPath});
  }
  visit(section.children, 0);
  return options;
};
