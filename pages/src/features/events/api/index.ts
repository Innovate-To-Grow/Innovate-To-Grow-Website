import { api } from '@/lib/api';
import {
  authApi,
  getStoredSession,
  isDefinitiveAuthFailure,
} from '@/features/auth';
import type {
  Registration,
  EventRegistrationOptions,
  EventRegistrationSummary,
  EventSchedulePayload,
} from './types';

export type {
  TicketOption,
  QuestionOption,
  RegistrationEvent,
  RegistrationTicket,
  RegistrationAnswer,
  Registration,
  MemberProfile,
  MemberPhone,
  EventRegistrationOptions,
  EventRegistrationSummary,
  ScheduleAgendaItem,
  ScheduleAgendaSection,
  ScheduleSlot,
  ScheduleTrack,
  ScheduleSection,
  ScheduleProjectRow,
  EventSchedulePayload,
} from './types';

// --- Types ---

// --- API Functions ---

// Deploy-skew fallback: a backend without /event/registration-events/ (route 404s) is the old
// single-event build, whose /event/registration-options/ returns the one live event or 404.
async function fetchRegistrationEventsFallback(): Promise<EventRegistrationSummary[]> {
  try {
    const options = await fetchRegistrationOptions();
    return [
      {
        id: options.id,
        name: options.name,
        slug: options.slug,
        date: options.date,
        end_date: options.end_date,
        location: options.location,
        description: options.description,
        registration: options.registration,
      },
    ];
  } catch (err: unknown) {
    const status = (err as {response?: {status?: number}}).response?.status;
    if (status === 404) {
      return [];
    }
    throw err;
  }
}

export async function fetchRegistrationEvents(): Promise<EventRegistrationSummary[]> {
  const hasSession = Boolean(getStoredSession());
  try {
    const response = hasSession
      ? await authApi.get<EventRegistrationSummary[]>('/event/registration-events/', {requireFreshIdentity: true})
      : await api.get<EventRegistrationSummary[]>('/event/registration-events/');
    return response.data;
  } catch (err: unknown) {
    const status = (err as {response?: {status?: number}}).response?.status;
    if (status === 401 && isDefinitiveAuthFailure(err)) {
      const response = await api.get<EventRegistrationSummary[]>('/event/registration-events/');
      return response.data;
    }
    if (status === 404) {
      return fetchRegistrationEventsFallback();
    }
    throw err;
  }
}

function normalizeRegistrationOptions(data: EventRegistrationOptions): EventRegistrationOptions {
  return {
    ...data,
    // Older servers coupled verification to required entry; preserve that behavior during rollout.
    require_phone: data.require_phone ?? Boolean(data.verify_phone),
    verify_secondary_email: data.verify_secondary_email ?? false,
    require_secondary_email: data.require_secondary_email ?? false,
  };
}

export async function fetchRegistrationOptions(eventSlug?: string | null): Promise<EventRegistrationOptions> {
  const hasSession = Boolean(getStoredSession());
  try {
    const config = {...(eventSlug ? {params: {event_slug: eventSlug}} : {})};
    const response = hasSession
      ? await authApi.get<EventRegistrationOptions>('/event/registration-options/', {
          ...config,
          requireFreshIdentity: true,
        })
      : await api.get<EventRegistrationOptions>('/event/registration-options/', config);
    return normalizeRegistrationOptions(response.data);
  } catch (err: unknown) {
    const status = (err as {response?: {status?: number}}).response?.status;
    // AllowAny may retry without credentials only after the refresh endpoint
    // definitively rejected this generation. Network/5xx failures and account
    // switches must not replace a member-aware view with anonymous data.
    if (status === 401 && isDefinitiveAuthFailure(err)) {
      const response = await api.get<EventRegistrationOptions>('/event/registration-options/', {
        ...(eventSlug ? {params: {event_slug: eventSlug}} : {}),
      });
      return normalizeRegistrationOptions(response.data);
    }
    throw err;
  }
}

export async function fetchCurrentSchedule(scheduleId?: string | null): Promise<EventSchedulePayload> {
  const response = await api.get<EventSchedulePayload>('/event/schedule/', {
    ...(scheduleId ? {params: {schedule_id: scheduleId}} : {}),
  });
  return response.data;
}

export async function createRegistration(data: {
  event_slug: string;
  ticket_id: string;
  attendee_first_name: string;
  attendee_last_name: string;
  attendee_organization?: string;
  answers: Array<{question_id: string; answer: string}>;
  attendee_secondary_email?: string;
  attendee_phone?: string;
  attendee_phone_region?: string;
  phone_verification_challenge_id?: string;
  secondary_email_verification_challenge_id?: string;
  secondary_email_verification_token?: string;
}): Promise<Registration> {
  const response = await authApi.post<Registration>('/event/registrations/', data);
  return response.data;
}

export async function fetchMyTickets(): Promise<Registration[]> {
  const response = await authApi.get<Registration[]>('/event/my-tickets/');
  return response.data;
}

export async function resendTicketEmail(registrationId: string): Promise<{message: string}> {
  const response = await authApi.post<{message: string}>(
    `/event/my-tickets/${registrationId}/resend-email/`,
    {},
  );
  return response.data;
}

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
