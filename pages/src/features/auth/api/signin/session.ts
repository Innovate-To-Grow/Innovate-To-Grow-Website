import {authApi} from '../session/client';
import {MalformedLoginResponseError} from '../contracts/errors';
import {clearTokens, getAccessToken, getStoredSession, persistAuthSession} from '../session/storage';
import type {LoginResponse} from '../contracts/types';

// Re-exported so callers (and test mocks) keep one module for the session lifecycle.
export {bootstrapAuthSession} from './bootstrapSession';
export type {BootstrapAuthResult} from './bootstrapSession';

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

/** What opening an SMS short link (`/l/<token>`) does: sign its member in, or send the visitor on. */
export type SmsLinkResult =
  | {kind: 'sign_in'; login: LoginResponse}
  | {kind: 'redirect'; redirectTo: string | null};

/**
 * Exchange an SMS short-link token. A personal link signs its member in once
 * (the session is stored, as for the emailed link); any other link answers
 * where to go. Rejects like `loginLinkAutoLogin` (the same failure codes).
 */
export const openSmsLink = async (token: string): Promise<SmsLinkResult> => {
  const response = await authApi.post<unknown>('/mail/sms-link/', {token}, {skipAuth: true});
  const body = asRecord(response.data);
  if (body?.kind === 'redirect') {
    return {
      kind: 'redirect',
      redirectTo: typeof body.redirect_to === 'string' ? body.redirect_to : null,
    };
  }
  const login = readLoginResponse(response.data);
  persistAuthSession(login);
  return {kind: 'sign_in', login};
};

/** Where the short `/register` link leads (Mail → SMS Settings); the sign-in page unless staff chose another. */
export const getRegisterLinkPath = async (): Promise<string | null> => {
  const response = await authApi.get<unknown>('/mail/register-link/', {skipAuth: true});
  const path = asRecord(response.data)?.path;
  return typeof path === 'string' ? path : null;
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
