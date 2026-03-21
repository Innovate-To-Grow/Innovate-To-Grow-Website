import api from './client';
import {getAccessToken} from '../auth';

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
  attendee_name: string;
  attendee_email: string;
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
