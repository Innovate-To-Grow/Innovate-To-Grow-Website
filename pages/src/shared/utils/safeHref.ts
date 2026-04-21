/**
 * Sanitize an href value sourced from CMS / RSS / admin input.
 *
 * React does not sanitize dynamic `href` values for dangerous URL schemes
 * (`javascript:`, `data:`, `vbscript:`, etc.). A compromised or malicious
 * API response could therefore inject a scheme that executes on click. This
 * helper enforces a scheme allowlist and returns `'#'` for anything else.
 *
 * Relative paths (`/foo`, `./bar`, `#section`) are accepted as-is.
 */
const SAFE_SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'];

export const safeHref = (url: unknown): string => {
  if (typeof url !== 'string') return '#';
  const trimmed = url.trim();
  if (!trimmed) return '#';

  // Allow fragment- and path-relative URLs without scheme.
  if (trimmed.startsWith('#') || trimmed.startsWith('/') || trimmed.startsWith('./') || trimmed.startsWith('../')) {
    return trimmed;
  }

  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (SAFE_SCHEMES.includes(parsed.protocol)) {
      return trimmed;
    }
  } catch {
    // Unparseable -> treat as unsafe.
  }
  return '#';
};
