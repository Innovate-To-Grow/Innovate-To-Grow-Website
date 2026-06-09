import type { EmailAuthSource, LoginResponse } from './types';

export const getSafeInternalRedirectPath = (value: string | null | undefined): string | null => {
  const normalized = value?.trim() ?? '';

  if (!normalized || !normalized.startsWith('/') || normalized.startsWith('//')) {
    return null;
  }

  return normalized;
};

export const buildCompleteProfilePath = (returnTo?: string | null): string => {
  const safeReturnTo = getSafeInternalRedirectPath(returnTo);
  if (!safeReturnTo) {
    return '/complete-profile';
  }
  return `/complete-profile?returnTo=${encodeURIComponent(safeReturnTo)}`;
};

export const buildLoginPath = (returnTo?: string | null): string => {
  // Send a login-gated page's visitor to /login with a sanitized returnTo so the
  // auth flow can bring them back where they started. Drops anything that isn't a
  // safe internal path (getSafeInternalRedirectPath rejects empty, off-site, and
  // protocol-relative values).
  const safeReturnTo = getSafeInternalRedirectPath(returnTo);
  return safeReturnTo ? `/login?returnTo=${encodeURIComponent(safeReturnTo)}` : '/login';
};

export const getPostAuthPath = (
  response: Pick<LoginResponse, 'next_step' | 'redirect_to' | 'requires_profile_completion'>,
  returnTo?: string | null,
  fallback = '/account',
): string => {
  // A page-supplied `returnTo` (e.g. the Past Projects login buttons) wins over the
  // backend `redirect_to`; it is preserved through the profile-completion detour too,
  // matching the register flow. Both values are sanitized before use.
  const safeReturnTo = getSafeInternalRedirectPath(returnTo);
  // Preserve the post-login destination when the server asks us to detour through
  // profile completion. Without this, magic/ticket/unsubscribe/impersonate logins
  // drop users at /account after completing their profile, even though `redirect_to`
  // (or a page `returnTo`) specified a real landing page. `buildCompleteProfilePath`
  // safely rejects a value that isn't an internal path.
  if (response.next_step === 'complete_profile' || response.requires_profile_completion) {
    return buildCompleteProfilePath(safeReturnTo ?? response.redirect_to);
  }
  return safeReturnTo ?? getSafeInternalRedirectPath(response.redirect_to) ?? fallback;
};

export const getEmailAuthSourcePath = (
  source: EmailAuthSource,
  response: Pick<LoginResponse, 'next_step' | 'redirect_to' | 'requires_profile_completion'>,
): string => {
  if (source === 'subscribe') {
    if (response.next_step === 'complete_profile' || response.requires_profile_completion) {
      return '/subscribe?step=profile';
    }
    return '/subscribe';
  }

  if (source === 'event_registration') {
    if (response.next_step === 'complete_profile' || response.requires_profile_completion) {
      return buildCompleteProfilePath('/event-registration');
    }
    return '/event-registration';
  }

  return getPostAuthPath(response);
};
