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

export const getPostAuthPath = (
  response: Pick<LoginResponse, 'next_step' | 'redirect_to' | 'requires_profile_completion'>,
  fallback = '/account',
): string => {
  if (response.next_step === 'complete_profile' || response.requires_profile_completion) {
    return buildCompleteProfilePath();
  }
  return getSafeInternalRedirectPath(response.redirect_to) ?? fallback;
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
    return '/event-registration';
  }

  return getPostAuthPath(response);
};
