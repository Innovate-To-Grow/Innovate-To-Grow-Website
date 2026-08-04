import {authApi, isDefinitiveAuthFailure} from './client';
import {
  clearTokens,
  getAccessToken,
  getStoredSession,
  persistAuthSession,
  updateStoredSessionProfile,
  type StoredAuthSession,
} from './storage';
import type {LoginResponse, UnsubscribeResponse, User} from './types';

export const loginLinkAutoLogin = async (
  token: string,
): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/mail/login-link/', {
    token,
  });
  persistAuthSession(response.data);
  return response.data;
};

export const unsubscribeAutoLogin = async (
  token: string,
): Promise<UnsubscribeResponse> => {
  const response = await authApi.post<UnsubscribeResponse>(
    '/authn/unsubscribe-login/',
    {token},
  );
  return response.data;
};

export const impersonateAutoLogin = async (
  token: string,
): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>(
    '/authn/impersonate-login/',
    {token},
  );
  persistAuthSession(response.data);
  return response.data;
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

  const user: User = {
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
  };

  const nestedRequires = candidate.requires_profile_completion;
  const explicitRequires =
    typeof payload.requires_profile_completion === 'boolean'
      ? payload.requires_profile_completion
      : typeof nestedRequires === 'boolean'
        ? nestedRequires
        : undefined;

  let requiresProfileCompletion = explicitRequires;
  if (
    requiresProfileCompletion === undefined &&
    ('first_name' in candidate ||
      'last_name' in candidate ||
      'organization' in candidate)
  ) {
    requiresProfileCompletion = !(
      readString(candidate, 'first_name', '').trim() &&
      readString(candidate, 'last_name', '').trim() &&
      readString(candidate, 'organization', '').trim()
    );
  }

  return {
    user,
    requiresProfileCompletion:
      requiresProfileCompletion ?? fallbackRequiresProfileCompletion,
  };
};

interface BootstrapInFlight {
  generation: string;
  promise: Promise<StoredAuthSession | null>;
}

let bootstrapInFlight: BootstrapInFlight | null = null;

const dispatchAuthStateChange = () => {
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};

/**
 * Verify the locally persisted generation against the backend and replace its
 * user/profile flags with the authoritative session payload. The auth client
 * refreshes an expired access token before retrying this request.
 */
export const bootstrapAuthSession =
  async (): Promise<StoredAuthSession | null> => {
    const snapshot = getStoredSession();
    if (!snapshot) return null;
    if (bootstrapInFlight?.generation === snapshot.generation) {
      return bootstrapInFlight.promise;
    }

    const promise: Promise<StoredAuthSession | null> = authApi
      .get<SessionPayload>('/authn/session/')
      .then((response) => {
        const current = getStoredSession();
        if (!current || current.generation !== snapshot.generation) {
          return current;
        }
        if (response.data.authenticated === false) {
          if (
            clearTokens({
              generation: current.generation,
              refresh: current.refresh,
            })
          ) {
            dispatchAuthStateChange();
          }
          return null;
        }

        const normalized = normalizeSessionUser(
          response.data,
          current.user,
          current.requires_profile_completion,
        );
        if (!normalized) return current;
        return updateStoredSessionProfile(
          {generation: current.generation, refresh: current.refresh},
          normalized.user,
          normalized.requiresProfileCompletion,
        );
      })
      .catch((error: unknown) => {
        const current = getStoredSession();
        if (!current || current.generation !== snapshot.generation) {
          return current;
        }
        if (
          isDefinitiveAuthFailure(error) &&
          clearTokens({
            generation: current.generation,
            refresh: current.refresh,
          })
        ) {
          dispatchAuthStateChange();
          return null;
        }
        // The interceptor clears a generation when refresh is rejected. For a
        // transient session-endpoint failure, retain only a locally valid access
        // session so an outage does not unnecessarily sign the member out.
        return isAuthenticated() ? current : null;
      })
      .finally(() => {
        if (bootstrapInFlight?.generation === snapshot.generation) {
          bootstrapInFlight = null;
        }
      });

    bootstrapInFlight = {generation: snapshot.generation, promise};
    return promise;
  };
