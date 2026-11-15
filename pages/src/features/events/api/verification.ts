import {authApi} from '@/features/auth';

export async function sendPhoneCode(
  phone: string,
  region: string,
  eventSlug: string,
): Promise<{detail: string; phone: string; challenge_id: string}> {
  const {withVerifiedSend} = await import('@/features/auth');
  return withVerifiedSend({
    operation: 'event.send_phone_code',
    destinationKind: 'phone',
    destination: phone,
    extraChallenge: {phone, region, event_slug: eventSlug},
    execute: async (verification) => {
      const response = await authApi.post<{detail: string; phone: string; challenge_id: string}>(
        '/event/send-phone-code/',
        {phone, region, event_slug: eventSlug, ...verification},
      );
      return response.data;
    },
  });
}

export async function verifyPhoneCode(
  phone: string,
  code: string,
  challengeId?: string,
  eventSlug?: string,
): Promise<{detail: string; verified: boolean; phone: string; challenge_id: string}> {
  const response = await authApi.post<{detail: string; verified: boolean; phone: string; challenge_id: string}>(
    '/event/verify-phone-code/',
    {
      phone,
      code,
      ...(challengeId ? {challenge_id: challengeId} : {}),
      ...(eventSlug ? {event_slug: eventSlug} : {}),
    },
  );
  return response.data;
}

export async function sendSecondaryEmailCode(
  email: string,
  eventSlug: string,
): Promise<{email: string; challenge_id: string}> {
  const {withVerifiedSend} = await import('@/features/auth');
  return withVerifiedSend({
    operation: 'event.send_secondary_email_code',
    destinationKind: 'email',
    destination: email,
    extraChallenge: {email, event_slug: eventSlug},
    execute: async (verification) => {
      const response = await authApi.post<{email: string; challenge_id: string}>(
        '/event/send-secondary-email-code/',
        {email, event_slug: eventSlug, ...verification},
      );
      return response.data;
    },
  });
}

export async function verifySecondaryEmailCode(
  email: string,
  code: string,
  challengeId: string,
  eventSlug: string,
): Promise<{email: string; verified: boolean; challenge_id: string; verification_token: string}> {
  const response = await authApi.post<{
    email: string; verified: boolean; challenge_id: string; verification_token: string;
  }>('/event/verify-secondary-email-code/', {
    email, code, challenge_id: challengeId, event_slug: eventSlug,
  });
  return response.data;
}
