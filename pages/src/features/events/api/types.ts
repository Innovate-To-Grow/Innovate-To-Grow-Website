// Types for the events API: registration options, registrations, and the event schedule.

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
  secondary_email_verified: boolean;
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
  require_phone: boolean;
  verify_secondary_email: boolean;
  require_secondary_email: boolean;
  tickets: TicketOption[];
  questions: QuestionOption[];
  registration: Registration | null;
  member_emails: string[];
  member_primary_email?: string;
  member_secondary_email: {email_address: string; verified: boolean} | null;
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
