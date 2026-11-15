// Pure response builders (no Playwright). Each returns a fully-typed object
// shaped like the real API response so specs stay declarative and a single
// `overrides` arg covers the per-test variation.
import type {
  ContactEmail,
  ContactPhone,
  LoginResponse,
  ProfileResponse,
  User,
} from '../../src/features/auth/api/contracts/types';
import type {
  EventRegistrationOptions,
  EventRegistrationSummary,
  Registration,
} from '../../src/features/events/api';

/**
 * A non-cryptographic JWT whose only meaningful content is the payload `exp`.
 * `isAuthenticated()` (session.ts) decodes ONLY `token.split('.')[1]` via
 * `atob` and checks `payload.exp > Date.now()/1000` — the signature is never
 * verified — so a far-future `exp` is enough to look "logged in". Login/verify
 * responses MUST carry one of these as `access`, or post-login state reads as
 * logged-out (menu won't flip, guarded pages bounce to /login).
 */
export function mintFakeJwt(opts: {exp?: number} = {}): string {
  const exp = opts.exp ?? Math.floor(Date.now() / 1000) + 86_400; // 24h ahead
  const header = Buffer.from(JSON.stringify({alg: 'HS256', typ: 'JWT'})).toString('base64');
  const payload = Buffer.from(JSON.stringify({exp, token_type: 'access'})).toString('base64');
  return `${header}.${payload}.sig`;
}

export function userResponse(overrides: Partial<User> = {}): User {
  return {member_uuid: 'member-e2e', email: 'member@example.com', ...overrides};
}

export function profileResponse(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    member_uuid: 'member-e2e',
    email: 'member@example.com',
    email_verified: true,
    primary_email_id: 'email-e2e',
    first_name: '',
    middle_name: '',
    last_name: '',
    organization: '',
    title: '',
    email_subscribe: false,
    is_staff: false,
    is_active: true,
    date_joined: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function loginResponse(overrides: Partial<LoginResponse> = {}): LoginResponse {
  const {user, ...rest} = overrides;
  return {
    message: 'Login successful.',
    access: mintFakeJwt(),
    refresh: 'refresh-e2e',
    user: userResponse(user),
    next_step: 'account',
    requires_profile_completion: false,
    ...rest,
  };
}

export function registrationOptions(
  overrides: Partial<EventRegistrationOptions> = {},
): EventRegistrationOptions {
  return {
    id: 'event-e2e',
    name: 'E2E Showcase',
    slug: 'e2e-showcase',
    date: '2026-05-01T18:00:00Z',
    location: 'E2E Hall',
    description: 'End-to-end smoke event.',
    allow_secondary_email: false,
    collect_phone: false,
    verify_phone: false,
    require_phone: false,
    verify_secondary_email: false,
    require_secondary_email: false,
    tickets: [{id: 'ticket-e2e', name: 'General Admission'}],
    questions: [],
    registration: null,
    member_emails: [],
    member_secondary_email: null,
    member_profile: null,
    member_phone: null,
    phone_regions: [{code: '1-US', label: 'United States'}],
    ...overrides,
  };
}

export function registrationEvent(
  overrides: Partial<EventRegistrationSummary> = {},
): EventRegistrationSummary {
  return {
    id: 'event-e2e',
    name: 'E2E Showcase',
    slug: 'e2e-showcase',
    date: '2026-05-01',
    location: 'E2E Hall',
    description: 'End-to-end smoke event.',
    registration: null,
    ...overrides,
  };
}

export function registration(overrides: Partial<Registration> = {}): Registration {
  return {
    id: 'registration-e2e',
    ticket_code: 'E2E-TICKET-001',
    attendee_first_name: 'Ada',
    attendee_last_name: 'Lovelace',
    attendee_name: 'Ada Lovelace',
    attendee_email: 'member@example.com',
    attendee_secondary_email: '',
    attendee_phone: '',
    phone_verified: false,
    secondary_email_verified: false,
    phone_verification_required: false,
    attendee_organization: 'Acme Corp',
    registered_at: '2026-05-01T18:05:00Z',
    ticket_email_sent_at: '2026-05-01T18:05:01Z',
    ticket_email_error: '',
    barcode_format: 'code128',
    barcode_image:
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    event: {
      id: 'event-e2e',
      name: 'E2E Showcase',
      slug: 'e2e-showcase',
      date: '2026-05-01T18:00:00Z',
      location: 'E2E Hall',
      description: 'End-to-end smoke event.',
    },
    ticket: {id: 'ticket-e2e', name: 'General Admission'},
    answers: [],
    ...overrides,
  };
}

// -- account emails / contacts ------------------------------------------

export function accountEmail(overrides: Partial<{email: string}> = {}): {email: string} {
  return {email: 'member@example.com', ...overrides};
}

export function contactEmail(overrides: Partial<ContactEmail> = {}): ContactEmail {
  return {
    id: 'cemail-e2e-1',
    email_address: 'work@example.com',
    email_type: 'secondary',
    subscribe: false,
    verified: false,
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

export function contactPhone(overrides: Partial<ContactPhone> = {}): ContactPhone {
  return {
    id: 'cphone-e2e-1',
    phone_number: '+12065551234',
    region: '1-US',
    region_display: 'United States',
    subscribe: false,
    verified: false,
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

// -- my tickets ----------------------------------------------------------

export function myTicket(overrides: Partial<Registration> = {}): Registration {
  return registration(overrides);
}
