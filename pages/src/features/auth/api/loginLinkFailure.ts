import {isAxiosError} from 'axios';

import {SessionNotSavedError} from './errors';
import {getSafeInternalRedirectPath} from './redirects';

export type LoginLinkFailureKind =
  | 'already_used'
  | 'expired'
  | 'invalid'
  | 'rate_limited'
  | 'unavailable'
  | 'session_not_saved';

export interface LoginLinkFailure {
  kind: LoginLinkFailureKind;
  /** Trying the same token again can succeed (rate limit, server or network fault). */
  retryable: boolean;
  /**
   * The link's own post-login destination, as a safe internal path. The backend
   * sends it (`redirect_to`) only with an expired or used link; every other
   * failure yields null, and so does an older backend.
   */
  redirectTo: string | null;
}

const RETRYABLE: ReadonlySet<LoginLinkFailureKind> = new Set([
  'rate_limited',
  'unavailable',
]);

const failure = (
  kind: LoginLinkFailureKind,
  redirectTo: string | null = null,
): LoginLinkFailure => ({kind, retryable: RETRYABLE.has(kind), redirectTo});

type BodyReason = 'already_used' | 'expired' | 'invalid';

/**
 * The backend names the reason in a machine-readable `code`, and that code is
 * authoritative: a known code decides even when the human-readable `detail`
 * says something else, and an unknown code is an invalid link. Only an older
 * backend, which sends `detail` alone, is read by its wording.
 */
function readReason(code: unknown, detail: unknown): BodyReason {
  if (typeof code === 'string') {
    if (code === 'already_used') return 'already_used';
    if (code === 'expired') return 'expired';
    return 'invalid';
  }
  const text = typeof detail === 'string' ? detail : '';
  if (/already been used/i.test(text)) return 'already_used';
  if (/expired/i.test(text)) return 'expired';
  return 'invalid';
}

/**
 * Sort a failed login-link exchange into what the visitor can do about it.
 * Pure: it reads the error and nothing else, so callers outside the API layer
 * never need Axios.
 *
 * Only a 400 is read for a reason; a 401 is never a used or expired link.
 */
export function classifyLoginLinkFailure(error: unknown): LoginLinkFailure {
  // The browser refused to store the session after the token was spent. This
  // is the only failure that is the browser's fault.
  if (error instanceof SessionNotSavedError) return failure('session_not_saved');

  // Every other non-HTTP failure (a 2xx body that is not a login, or anything
  // unexpected) is transient from the visitor's point of view: the token is at
  // worst spent, and a retry then reports it as used.
  if (!isAxiosError(error)) return failure('unavailable');

  const status = error.response?.status;
  // No response: offline, DNS, CORS, or timeout.
  if (status === undefined) return failure('unavailable');
  // The exchange is not throttled by client IP (a whole campus shares one), so
  // this is an edge proxy or WAF answering in its own words: the body, JSON or
  // not, is never read, and a later try can succeed.
  if (status === 429) return failure('rate_limited');
  // 408 is a server-side request timeout: transient, like a 5xx.
  if (status === 408 || status >= 500) return failure('unavailable');
  // Everything else that is not a 400 is terminal on purpose. 401 is never a
  // used or expired link, and a retry cannot change a 403 (a WAF or CDN block)
  // or a 404 (a missing route). The visitor is not stranded either way: every
  // terminal failure offers the email-code sign-in.
  if (status !== 400) return failure('invalid');

  const body: unknown = error.response?.data;
  const {code, detail, redirect_to} =
    body && typeof body === 'object'
      ? (body as {code?: unknown; detail?: unknown; redirect_to?: unknown})
      : {code: undefined, detail: undefined, redirect_to: undefined};
  const reason = readReason(code, detail);
  if (reason === 'invalid') return failure('invalid');

  // Only an expired or used link carries its destination; an invalid one must
  // stay indistinguishable from an unknown token, so nothing is read from it.
  return failure(
    reason,
    typeof redirect_to === 'string'
      ? getSafeInternalRedirectPath(redirect_to)
      : null,
  );
}
