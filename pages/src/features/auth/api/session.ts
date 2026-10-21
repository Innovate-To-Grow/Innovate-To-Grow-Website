import {authApi, isDefinitiveAuthFailure} from './client';
import {MalformedLoginResponseError} from './errors';
import {
  clearTokens,
  getAccessToken,
  getStoredSession,
  persistAuthSession,
  updateStoredSessionProfile,
  type StoredAuthSession,
} from './storage';
import type {LoginResponse, User} from './types';

/**
 * A 2xx answer is only a login when it carries the fields a session is built
 * from. Anything else (a proxy or captive portal answering with HTML, an SPA
 * rewrite) must not reach storage: persisting it would either throw a
 * confusing TypeError or store a session that cannot be read back. The check
 * mirrors what `storage.ts` requires of a stored user.
 */
const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : null;

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value !== '';

const hasLoginTokens = (candidate: Record<string, unknown>) =>
  isNonEmptyString(candidate.access) && isNonEmptyString(candidate.refresh);

const hasStoredUserFields = (user: Record<string, unknown>) =>
  typeof user.member_uuid === 'string' && typeof user.email === 'string';

const readLoginResponse = (data: unknown): LoginResponse => {
  const candidate = asRecord(data);
  const user = asRecord(candidate?.user);
  if (
    !candidate ||
    !user ||
    !hasLoginTokens(candidate) ||
    !hasStoredUserFields(user)
  ) {
    throw new MalformedLoginResponseError();
  }
  return data as LoginResponse;
};

/**
 * Exchange the emailed one-time token for a session and store it.
 *
 * Rejects with an Axios error when the exchange fails, with
 * `MalformedLoginResponseError` when the server answers 2xx with something that
 * is not a login, and with `SessionNotSavedError` when the browser refuses to
 * store the session after the token was already spent.
 */
export const loginLinkAutoLogin = async (
  token: string,
): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>(
    '/mail/login-link/',
    {token},
    {skipAuth: true},
  );
  const login = readLoginResponse(response.data);
  persistAuthSession(login);
  return login;
};

export const impersonateAutoLogin = async (
  token: string,
): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>(
    '/authn/impersonate-login/',
    {token},
    {skipAuth: true},
  );
  const login = readLoginResponse(response.data);
  persistAuthSession(login);
  return login;
};

export const logout = async (): Promise<void> => {
  // Capture the exact generation being logged out. A concurrent login in this
  // tab or another tab must not be cleared by this operation.
  const snapshot = getStoredSession();
  const cleared = clearTokens(
    snapshot
      ? {generation: snapshot.generation, refresh: snapshot.refresh}
      : undefined,
  );
  if (cleared) window.dispatchEvent(new Event('i2g-auth-state-change'));

  if (snapshot?.refresh) {
    void authApi
      .post('/authn/logout/', {refresh: snapshot.refresh})
      .catch(() => {
        /* noop — the guarded local logout already completed */
      });
  }
};

const decodeJwtPayload = (token: string): {exp?: unknown} | null => {
  try {
    const encoded = token.split('.')[1];
    if (!encoded) return null;
    const normalized = encoded.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      '=',
    );
    return JSON.parse(atob(padded)) as {exp?: unknown};
  } catch {
    return null;
  }
};

export const isAuthenticated = (): boolean => {
  const token = getAccessToken();
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  return (
    typeof payload?.exp === 'number' &&
    payload.exp > Date.now() / 1000
  );
};

type SessionPayload = Record<string, unknown> & {
  authenticated?: boolean;
  user?: unknown;
  profile?: unknown;
  requires_profile_completion?: unknown;
};

const asObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : null;

const readString = (
  candidate: Record<string, unknown>,
  key: string,
  fallback: string,
) => {
  const value = candidate[key];
  return typeof value === 'string' ? value : fallback;
};

const readOptionalString = (
  candidate: Record<string, unknown>,
  key: string,
  fallback: string | undefined,
) => {
  if (!(key in candidate)) return fallback;
  const value = candidate[key];
  return typeof value === 'string' ? value : undefined;
};

const readSessionUser = (
  candidate: Record<string, unknown>,
  memberUuid: string,
  fallback: User,
): User => ({
  ...fallback,
  member_uuid: memberUuid,
  email: readString(candidate, 'email', fallback.email),
  phone: readOptionalString(candidate, 'phone', fallback.phone),
  profile_image: readOptionalString(
    candidate,
    'profile_image',
    fallback.profile_image,
  ),
  is_staff:
    typeof candidate.is_staff === 'boolean'
      ? candidate.is_staff
      : fallback.is_staff,
  first_name: readOptionalString(candidate, 'first_name', fallback.first_name),
  last_name: readOptionalString(candidate, 'last_name', fallback.last_name),
});

/**
 * The explicit flag (top-level, then on the user), else derived from the
 * profile fields the payload carries; undefined when it carries neither, so
 * the stored flag is kept.
 */
const readRequiresProfileCompletion = (
  payload: SessionPayload,
  candidate: Record<string, unknown>,
): boolean | undefined => {
  if (typeof payload.requires_profile_completion === 'boolean')
    return payload.requires_profile_completion;
  const nestedRequires = candidate.requires_profile_completion;
  if (typeof nestedRequires === 'boolean') return nestedRequires;
  if (
    !(
      'first_name' in candidate ||
      'last_name' in candidate ||
      'organization' in candidate
    )
  )
    return undefined;
  return !(
    readString(candidate, 'first_name', '').trim() &&
    readString(candidate, 'last_name', '').trim() &&
    readString(candidate, 'organization', '').trim()
  );
};

const normalizeSessionUser = (
  payload: SessionPayload,
  fallback: User,
  fallbackRequiresProfileCompletion: boolean,
): {user: User; requiresProfileCompletion: boolean} | null => {
  const candidate =
    asObject(payload.user) ?? asObject(payload.profile) ?? asObject(payload);
  if (!candidate) return null;

  const memberUuid = readString(candidate, 'member_uuid', fallback.member_uuid);
  if (!memberUuid) return null;

  return {
    user: readSessionUser(candidate, memberUuid, fallback),
    requiresProfileCompletion:
      readRequiresProfileCompletion(payload, candidate) ??
      fallbackRequiresProfileCompletion,
  };
};

interface BootstrapInFlight {
  generation: string;
  promise: Promise<BootstrapAuthResult>;
}

export type BootstrapAuthResult =
  | {status: 'verified'; session: StoredAuthSession}
  | {status: 'anonymous'; session: null}
  | {status: 'unverified'; session: StoredAuthSession};

let bootstrapInFlight: BootstrapInFlight | null = null;

const dispatchAuthStateChange = () => {
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};

const ANONYMOUS: BootstrapAuthResult = {status: 'anonymous', session: null};

/**
 * When the stored session is no longer the one being verified, report it as
 * it is (or anonymous).
 */
const supersededResult = (
  current: StoredAuthSession | null,
  snapshot: StoredAuthSession,
): BootstrapAuthResult | null => {
  if (current && current.generation === snapshot.generation) return null;
  return current ? {status: 'unverified', session: current} : ANONYMOUS;
};

const applySessionPayload = (
  current: StoredAuthSession,
  data: SessionPayload,
): BootstrapAuthResult => {
  if (data.authenticated === false) {
    if (
      clearTokens({generation: current.generation, refresh: current.refresh})
    ) {
      dispatchAuthStateChange();
    }
    return ANONYMOUS;
  }
  const normalized = normalizeSessionUser(
    data,
    current.user,
    current.requires_profile_completion,
  );
  if (!normalized) return {status: 'verified', session: current};
  const session = updateStoredSessionProfile(
    {generation: current.generation, refresh: current.refresh},
    normalized.user,
    normalized.requiresProfileCompletion,
  );
  return session ? {status: 'verified', session} : ANONYMOUS;
};

const bootstrapFailureResult = (
  current: StoredAuthSession,
  error: unknown,
): BootstrapAuthResult => {
  if (
    isDefinitiveAuthFailure(error) &&
    clearTokens({generation: current.generation, refresh: current.refresh})
  ) {
    dispatchAuthStateChange();
    return ANONYMOUS;
  }
  // A transient failure preserves display identity, but never establishes
  // authoritative authentication for protected client behavior.
  return {status: 'unverified', session: current};
};

/**
 * Verify the locally persisted generation against the backend and replace its
 * user/profile flags with the authoritative session payload. The auth client
 * refreshes an expired access token before retrying this request.
 */
export const bootstrapAuthSession =
  async (): Promise<BootstrapAuthResult> => {
    const snapshot = getStoredSession();
    if (!snapshot) return {status: 'anonymous', session: null};
    if (bootstrapInFlight?.generation === snapshot.generation) {
      return bootstrapInFlight.promise;
    }

    const promise: Promise<BootstrapAuthResult> = authApi
      .get<SessionPayload>('/authn/session/')
      .then<BootstrapAuthResult>((response) => {
        const current = getStoredSession();
        return (
          supersededResult(current, snapshot) ??
          applySessionPayload(current as StoredAuthSession, response.data)
        );
      })
      .catch((error: unknown): BootstrapAuthResult => {
        const current = getStoredSession();
        return (
          supersededResult(current, snapshot) ??
          bootstrapFailureResult(current as StoredAuthSession, error)
        );
      })
      .finally(() => {
        if (bootstrapInFlight?.generation === snapshot.generation) {
          bootstrapInFlight = null;
        }
      });

    bootstrapInFlight = {generation: snapshot.generation, promise};
    return promise;
  };
