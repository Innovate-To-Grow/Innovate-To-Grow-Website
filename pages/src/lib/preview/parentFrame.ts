// Trust rules for the admin preview frames (/_block-preview, /_footer-preview): which parent
// windows may post content to the frame, and where the frame announces itself.

// postMessage origin allowlist, frozen at module load.
//
// Same-origin is always trusted (covers dev via the Vite proxy and prod
// deployments where admin and SPA share a host). Split frontend/backend
// setups run the Django admin on the backend origin while the iframe is hosted
// by the frontend origin. `VITE_API_BASE_URL` is already required for frontend
// production builds, so its origin is trusted as the default admin parent.
// `VITE_ADMIN_ORIGIN` remains available for nonstandard admin origins
// (comma-separated if there are multiple), e.g. "https://admin.example.com".
function parseAllowedOrigins(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((o) => normalizeOrigin(o))
    .filter(Boolean);
}

export function normalizeOrigin(raw: string): string {
  try {
    const url = new URL(String(raw || '').trim());
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    return url.origin.replace(/\/+$/, '');
  } catch {
    return '';
  }
}

function isLoopbackHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
}

function isTrustedDevLoopbackOrigin(origin: string): boolean {
  if (!import.meta.env.DEV) return false;

  try {
    const iframeOrigin = new URL(window.location.origin);
    const parentOrigin = new URL(origin);
    return (
      iframeOrigin.protocol === 'http:' &&
      parentOrigin.protocol === 'http:' &&
      isLoopbackHost(iframeOrigin.hostname) &&
      isLoopbackHost(parentOrigin.hostname)
    );
  } catch {
    return false;
  }
}

const SAME_ORIGIN = normalizeOrigin(window.location.origin);
const CONFIGURED_PARENT_ORIGINS = [
  ...parseAllowedOrigins(import.meta.env.VITE_ADMIN_ORIGIN),
  normalizeOrigin(import.meta.env.VITE_API_BASE_URL),
].filter(Boolean);
const ALLOWED_PARENT_ORIGINS = new Set<string>([
  SAME_ORIGIN,
  ...CONFIGURED_PARENT_ORIGINS,
]);

export function isTrustedParentOrigin(origin: string): boolean {
  const normalizedOrigin = normalizeOrigin(origin);
  if (!normalizedOrigin) return false;
  return ALLOWED_PARENT_ORIGINS.has(normalizedOrigin) || isTrustedDevLoopbackOrigin(normalizedOrigin);
}

export function getTrustedReferrerOrigin(): string {
  const referrerOrigin = normalizeOrigin(document.referrer);
  return referrerOrigin && isTrustedParentOrigin(referrerOrigin) ? referrerOrigin : '';
}

export function getInitialReadyTargetOrigins(): string[] {
  const referrerOrigin = getTrustedReferrerOrigin();
  if (referrerOrigin) return [referrerOrigin];
  if (CONFIGURED_PARENT_ORIGINS.length > 0) return [...CONFIGURED_PARENT_ORIGINS];
  return [SAME_ORIGIN || window.location.origin];
}

export function getExpectedPreviewNonce(): string {
  const nonce = new URLSearchParams(window.location.search)
    .get('nonce')
    ?.trim();
  return nonce && nonce.length <= 256 ? nonce : '';
}
