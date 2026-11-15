import {MemoryRouter} from 'react-router';
import {vi} from 'vitest';
import type {FormEvent, ReactNode} from 'react';

import type {EventRegistrationOptions, Registration} from '@/features/events/api';

export const demoEvent = {
  id: 'event-1',
  name: 'Demo Day',
  slug: 'demo-day',
  date: '2026-05-01',
  location: 'Campus',
  description: 'Event description',
  registration: null,
};

export const baseOptions: EventRegistrationOptions = {
  id: 'event-1',
  name: 'Demo Day',
  slug: 'demo-day',
  date: '2026-05-01',
  location: 'Campus',
  description: 'Event description',
  allow_secondary_email: false,
  collect_phone: false,
  verify_phone: false,
  require_phone: false,
  verify_secondary_email: false,
  require_secondary_email: false,
  tickets: [{id: 'ticket-1', name: 'General Admission'}],
  questions: [],
  registration: null,
  member_emails: [],
  member_secondary_email: null,
  member_profile: null,
  member_phone: null,
  phone_regions: [{code: '1-US', label: 'United States'}],
};

const memberProfile = {
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Acme',
  title: 'Engineer',
};

export const registrationFixture = (overrides: Partial<Registration> = {}): Registration => ({
  id: 'registration-1',
  ticket_code: 'I2G-TEST',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: '',
  attendee_phone: '',
  phone_verified: false,
  secondary_email_verified: false,
  phone_verification_required: false,
  attendee_organization: 'Acme',
  registered_at: '2026-05-01T12:00:00Z',
  ticket_email_sent_at: null,
  ticket_email_error: '',
  barcode_format: 'PDF417',
  barcode_image: 'data:image/png;base64,test',
  event: {...demoEvent},
  ticket: {id: 'ticket-1', name: 'General Admission'},
  answers: [],
  ...overrides,
});

export const formOptions = (overrides: Partial<EventRegistrationOptions> = {}): EventRegistrationOptions => ({
  ...baseOptions,
  member_emails: ['ada@example.com'],
  member_secondary_email: null,
  member_profile: {...memberProfile},
  ...overrides,
});

export const wrapper = ({children}: {children?: ReactNode}) => (
  <MemoryRouter initialEntries={['/event-registration']}>{children}</MemoryRouter>
);

export const fakeEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

export const emailSignIn = () => ({
  access: 'access-token',
  refresh: 'refresh-token',
  user: {member_uuid: 'member-1', email: 'ada@example.com'},
  next_step: 'complete_profile',
  requires_profile_completion: true,
});

export const phoneSignIn = () => ({
  access: 'access-token',
  refresh: 'refresh-token',
  user: {member_uuid: 'member-1', phone: '+12025550123'},
  next_step: 'complete_profile',
  requires_profile_completion: true,
});
