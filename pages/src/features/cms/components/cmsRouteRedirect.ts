const REDIRECT_CHAIN_STORAGE_KEY = 'i2g:cms-route-redirect-chain';
const REDIRECT_CHAIN_MAX_AGE_MS = 30_000;
const MAX_REDIRECT_CHAIN_LENGTH = 16;

function hasControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const code = character.charCodeAt(0);
    return code <= 0x1f || code === 0x7f;
  });
}

interface RedirectLocation {
  origin: string;
  pathname: string;
  search: string;
  hash: string;
  replace(url: string): void;
}

interface RedirectChain {
  expectedHref: string;
  visitedPaths: string[];
  updatedAt: number;
}

export type CMSRouteRedirectResult =
  | 'redirected'
  | 'invalid'
  | 'self_redirect'
  | 'redirect_loop';

function currentHref(location: RedirectLocation): string {
  return `${location.pathname}${location.search}${location.hash}`;
}

function comparablePath(pathname: string): string {
  let decoded = pathname;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    // A malformed current browser path will not compare equal to a valid target.
  }
  return decoded === '/' ? decoded : decoded.replace(/\/+$/, '');
}

/** A redirect target must be a plain same-site path: no scheme-relative URL, query, fragment or escapes. */
function isUnsafeTarget(target: string): boolean {
  return (
    !target.startsWith('/')
    || target.startsWith('//')
    || target.includes('\\')
    || target.includes('?')
    || target.includes('#')
    || hasControlCharacter(target)
  );
}

/** A path segment that decodes to a traversal, a separator or a control character (or does not decode). */
function hasUnsafeSegment(target: string): boolean {
  return target.split('/').filter(Boolean).some((rawSegment) => {
    let segment: string;
    try {
      segment = decodeURIComponent(rawSegment);
    } catch {
      return true;
    }
    return (
      segment === '.'
      || segment === '..'
      || segment.includes('/')
      || segment.includes('\\')
      || hasControlCharacter(segment)
    );
  });
}

function destinationPath(redirectTo: string, location: RedirectLocation): string | null {
  const target = redirectTo.trim();
  if (isUnsafeTarget(target) || hasUnsafeSegment(target)) {
    return null;
  }

  try {
    const parsed = new URL(target, location.origin);
    if (parsed.origin !== location.origin || parsed.search || parsed.hash) {
      return null;
    }
    return parsed.pathname;
  } catch {
    return null;
  }
}

function readRedirectChain(
  storage: Storage | null,
  href: string,
  now: number,
): RedirectChain | null {
  if (!storage) return null;

  try {
    const raw = storage.getItem(REDIRECT_CHAIN_STORAGE_KEY);
    if (!raw) return null;
    const candidate = JSON.parse(raw) as Partial<RedirectChain>;
    if (
      candidate.expectedHref !== href
      || typeof candidate.updatedAt !== 'number'
      || now - candidate.updatedAt > REDIRECT_CHAIN_MAX_AGE_MS
      || !Array.isArray(candidate.visitedPaths)
      || candidate.visitedPaths.length > MAX_REDIRECT_CHAIN_LENGTH
      || !candidate.visitedPaths.every((path) => typeof path === 'string')
    ) {
      return null;
    }
    return candidate as RedirectChain;
  } catch {
    return null;
  }
}

function getSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function removeRedirectChain(storage: Storage | null): void {
  if (!storage) return;
  try {
    storage.removeItem(REDIRECT_CHAIN_STORAGE_KEY);
  } catch {
    // Redirects still work when storage is disabled; only cross-load loop
    // detection is unavailable in that browser mode.
  }
}

export function clearCMSRouteRedirectChain(): void {
  removeRedirectChain(getSessionStorage());
}

function saveRedirectChain(storage: Storage | null, chain: RedirectChain): void {
  if (!storage) return;
  try {
    storage.setItem(REDIRECT_CHAIN_STORAGE_KEY, JSON.stringify(chain));
  } catch {
    // Continue without the cross-load loop guard when storage is unavailable.
  }
}

export function performCMSRouteRedirect(
  redirectTo: string,
  location: RedirectLocation = window.location,
  storage: Storage | null = getSessionStorage(),
  now = Date.now(),
): CMSRouteRedirectResult {
  const pathname = destinationPath(redirectTo, location);
  if (!pathname) {
    removeRedirectChain(storage);
    return 'invalid';
  }

  const currentPath = comparablePath(location.pathname);
  const targetPath = comparablePath(pathname);
  if (currentPath === targetPath) {
    removeRedirectChain(storage);
    return 'self_redirect';
  }

  const href = currentHref(location);
  const previousChain = readRedirectChain(storage, href, now);
  const visitedPaths = previousChain
    ? [...previousChain.visitedPaths, currentPath]
    : [currentPath];

  if (
    visitedPaths.includes(targetPath)
    || visitedPaths.length >= MAX_REDIRECT_CHAIN_LENGTH
  ) {
    removeRedirectChain(storage);
    return 'redirect_loop';
  }

  const targetHref = `${pathname}${location.search}${location.hash}`;
  saveRedirectChain(storage, {expectedHref: targetHref, visitedPaths, updatedAt: now});

  try {
    location.replace(targetHref);
  } catch (error) {
    removeRedirectChain(storage);
    throw error;
  }
  return 'redirected';
}
