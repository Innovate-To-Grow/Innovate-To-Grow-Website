import { api } from '@/lib/api';
import {
  authApi,
  getStoredSession,
  isDefinitiveAuthFailure,
} from '@/features/auth';

// --- Types ---

export interface TicketOption {
  id: string;
  name: string;
}

export interface QuestionOption {
  id: string;
  text: string;
  is_required: boolean;
  order: number;
}

export interface RegistrationEvent {
  id: string;
  name: string;
  slug: string;
  date: string;
  end_date?: string;
  location: string;
  description: string;
}

export interface RegistrationTicket {
  id: string;
  name: string;
}

export interface RegistrationAnswer {
  question_id: string;
  question_text: string;
  answer: string;
}

export interface Registration {
  id: string;
  ticket_code: string;
  attendee_first_name: string;
  attendee_last_name: string;
  attendee_name: string;
  attendee_email: string;
  attendee_secondary_email: string;
  attendee_phone: string;
  phone_verified: boolean;
  phone_verification_required: boolean;
  attendee_organization: string;
  registered_at: string;
  ticket_email_sent_at: string | null;
  ticket_email_error: string;
  barcode_format: string;
  barcode_image: string;
  event: RegistrationEvent;
  ticket: RegistrationTicket;
  answers: RegistrationAnswer[];
}

export interface MemberProfile {
  first_name: string;
  middle_name: string;
  last_name: string;
  organization: string;
  title: string;
}

export interface MemberPhone {
  phone_number: string;
  region: string;
  verified: boolean;
}

export interface EventRegistrationOptions {
  id: string;
  name: string;
  slug: string;
  date: string;
  end_date?: string;
  location: string;
  description: string;
  allow_secondary_email: boolean;
  collect_phone: boolean;
  verify_phone: boolean;
  tickets: TicketOption[];
  questions: QuestionOption[];
  registration: Registration | null;
  member_emails: string[];
  member_profile: MemberProfile | null;
  member_phone: MemberPhone | null;
  phone_regions: Array<{code: string; label: string}>;
}

export interface EventRegistrationSummary extends RegistrationEvent {
  registration: Registration | null;
}

export interface ScheduleAgendaItem {
  id: string;
  time: string;
  title: string;
  location: string;
}

export interface ScheduleAgendaSection {
  title: string;
  location: string;
  items: ScheduleAgendaItem[];
}

export interface ScheduleSlot {
  id: string;
  order: number;
  is_break: boolean;
  display_text: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  tooltip: string;
  project_id: string | null;
}

export interface ScheduleTrack {
  id: string;
  track_number: number;
  label: string;
  room: string;
  zoom_link: string;
  topic: string;
  winner: string;
  display_order: number;
  slots: ScheduleSlot[];
}

export interface ScheduleSection {
  id: string;
  code: string;
  label: string;
  display_order: number;
  start_time: string;
  slot_minutes: number;
  accent_color: string;
  max_order: number;
  tracks: ScheduleTrack[];
}

export interface ScheduleProjectRow {
  id: string;
  track: number;
  order: number;
  year_semester: string;
  class_code: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  is_presenting: boolean;
  tooltip: string;
}

export interface EventSchedulePayload {
  event: RegistrationEvent;
  show_winners: boolean;
  grand_winners: {section: string; winner: string}[];
  expo: ScheduleAgendaSection;
  presentations_title: string;
  sections: ScheduleSection[];
  awards: ScheduleAgendaSection;
  projects: ScheduleProjectRow[];
}

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
    const response = await (hasSession ? authApi : api).get<EventRegistrationSummary[]>(
      '/event/registration-events/',
    );
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

export async function fetchRegistrationOptions(eventSlug?: string | null): Promise<EventRegistrationOptions> {
  const hasSession = Boolean(getStoredSession());
  try {
    const response = await (hasSession ? authApi : api).get<EventRegistrationOptions>('/event/registration-options/', {
      ...(eventSlug ? {params: {event_slug: eventSlug}} : {}),
    });
    return response.data;
  } catch (err: unknown) {
    const status = (err as {response?: {status?: number}}).response?.status;
    // AllowAny may retry without credentials only after the refresh endpoint
    // definitively rejected this generation. Network/5xx failures and account
    // switches must not replace a member-aware view with anonymous data.
    if (status === 401 && isDefinitiveAuthFailure(err)) {
      const response = await api.get<EventRegistrationOptions>('/event/registration-options/', {
        ...(eventSlug ? {params: {event_slug: eventSlug}} : {}),
      });
      return response.data;
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
  const {withVerifiedSend} = await import('@/features/auth/verification');
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
