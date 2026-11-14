const SMS_CHALLENGE_PREFIX = 'i2g_sms_challenge:';

const storageKey = (scope: string) =>
  `${SMS_CHALLENGE_PREFIX}${encodeURIComponent(scope)}`;

const normalizeChallengeId = (
  challengeId: unknown,
): string | undefined => {
  if (typeof challengeId !== 'string') return undefined;
  const normalized = challengeId.trim();
  return normalized && normalized.length <= 128 ? normalized : undefined;
};

export const phoneAuthChallengeScope = (
  phoneNumber: string,
  region: string,
) => `phone-auth:${region}:${phoneNumber}`;

export const contactPhoneChallengeScope = (id: string) =>
  `contact-phone:${id}`;

export const passwordChangeChallengeScope = (email?: string) =>
  `password-change:${email?.trim().toLowerCase() || 'current-account'}`;

export const passwordResetChallengeScope = (identifier: string) =>
  `password-reset:${identifier.trim().toLowerCase()}`;

/**
 * Keep SMS challenge identifiers in tab-scoped storage. They survive a route
 * transition or refresh, but are not shared across tabs or long-lived with an
 * auth session.
 */
export const rememberSmsChallenge = (
  scope: string,
  challengeId: unknown,
): string | undefined => {
  const normalized = normalizeChallengeId(challengeId);
  try {
    if (normalized) {
      sessionStorage.setItem(storageKey(scope), normalized);
    } else {
      sessionStorage.removeItem(storageKey(scope));
    }
  } catch {
    // Storage may be denied. Callers retain the response and can still pass an
    // explicit challenge ID; legacy verification remains available otherwise.
  }
  return normalized;
};

export const readSmsChallenge = (scope: string): string | undefined => {
  try {
    return normalizeChallengeId(sessionStorage.getItem(storageKey(scope)));
  } catch {
    return undefined;
  }
};

export const forgetSmsChallenge = (
  scope: string,
  expectedChallengeId?: string,
): void => {
  try {
    if (
      expectedChallengeId &&
      sessionStorage.getItem(storageKey(scope)) !== expectedChallengeId
    ) {
      return;
    }
    sessionStorage.removeItem(storageKey(scope));
  } catch {
    // Storage may be denied.
  }
};
