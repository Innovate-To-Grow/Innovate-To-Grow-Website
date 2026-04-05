import api from '../../shared/api/client';
import {getAccessToken} from '../../services/auth';

// --- Types ---

export interface TicketOption {
  id: string;
  name: string;
  price: string;
  quantity: number;
  remaining_quantity: number | null;
  is_sold_out: boolean;
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
  location: string;
  description: string;
}

export interface RegistrationTicket {
  id: string;
  name: string;
  price: string;
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

export interface EventRegistrationOptions {
  id: string;
  name: string;
  slug: string;
  date: string;
  location: string;
  description: string;
  tickets: TicketOption[];
  questions: QuestionOption[];
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
  tooltip: string;
}

export interface EventSchedulePayload {
  event: RegistrationEvent;
  show_winners: boolean;
  expo: ScheduleAgendaSection;
  presentations_title: string;
  sections: ScheduleSection[];
  awards: ScheduleAgendaSection;
  projects: ScheduleProjectRow[];
}

// --- API Functions ---

function authHeaders() {
  const token = getAccessToken();
  return token ? {Authorization: `Bearer ${token}`} : {};
}

export async function fetchRegistrationOptions(): Promise<EventRegistrationOptions> {
  const response = await api.get<EventRegistrationOptions>('/event/registration-options/', {
    headers: authHeaders(),
  });
  return response.data;
}

export async function fetchCurrentSchedule(): Promise<EventSchedulePayload> {
  const response = await api.get<EventSchedulePayload>('/event/schedule/');
  return response.data;
}

export async function createRegistration(data: {
  event_slug: string;
  ticket_id: string;
  answers: Array<{question_id: string; answer: string}>;
}): Promise<Registration> {
  const response = await api.post<Registration>('/event/registrations/', data, {
    headers: authHeaders(),
  });
  return response.data;
}

export async function fetchMyTickets(): Promise<Registration[]> {
  const response = await api.get<Registration[]>('/event/my-tickets/', {
    headers: authHeaders(),
  });
  return response.data;
}

export async function resendTicketEmail(registrationId: string): Promise<{message: string}> {
  const response = await api.post<{message: string}>(
    `/event/my-tickets/${registrationId}/resend-email/`,
    {},
    {headers: authHeaders()},
  );
  return response.data;
}
