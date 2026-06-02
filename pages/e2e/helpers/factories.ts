// Pure response builders (no Playwright). Each returns a fully-typed object
// shaped like the real API response so specs stay declarative and a single
// `overrides` arg covers the per-test variation.
import type {LoginResponse, ProfileResponse, User} from '../../src/features/auth/api/types';
import type {
  EventRegistrationOptions,
  EventSchedulePayload,
  Registration,
} from '../../src/features/events/api';
import type {NewsArticle, PaginatedResponse} from '../../src/features/news/api';
import type {ProjectDetail, ProjectTableRow} from '../../src/features/projects/api';
import type {CMSPageResponse} from '../../src/features/cms/api';

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
    tickets: [{id: 'ticket-e2e', name: 'General Admission'}],
    questions: [],
    registration: null,
    member_emails: [],
    member_profile: null,
    member_phone: null,
    phone_regions: [{code: '1-US', label: 'United States'}],
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

export function newsArticle(overrides: Partial<NewsArticle> = {}): NewsArticle {
  return {
    id: 'news-e2e-1',
    title: 'E2E News Headline',
    source_url: 'https://news.ucmerced.edu/e2e',
    summary: 'A concise summary of the E2E news article.',
    image_url: '',
    author: 'Newsroom',
    published_at: '2026-04-01T12:00:00Z',
    ...overrides,
  };
}

export function newsList(
  options: {count?: number; page?: number; pageSize?: number; results?: NewsArticle[]} = {},
): PaginatedResponse<NewsArticle> {
  const pageSize = options.pageSize ?? 12;
  const page = options.page ?? 1;
  const results =
    options.results ??
    Array.from({length: Math.min(pageSize, options.count ?? 3)}, (_, i) =>
      newsArticle({id: `news-e2e-${(page - 1) * pageSize + i + 1}`, title: `E2E News ${(page - 1) * pageSize + i + 1}`}),
    );
  const count = options.count ?? results.length;
  return {
    count,
    next: page * pageSize < count ? `/news/?page=${page + 1}&page_size=${pageSize}` : null,
    previous: page > 1 ? `/news/?page=${page - 1}&page_size=${pageSize}` : null,
    results,
  };
}

export function pastProjectRows(): ProjectTableRow[] {
  return [
    {
      id: 'project-e2e-1',
      semester_label: '2025 Fall',
      class_code: 'CSE 120',
      team_number: '7',
      team_name: 'Team Helix',
      project_title: 'Adaptive Irrigation Dashboard',
      organization: 'Acme Corp',
      industry: 'Agriculture',
      abstract: 'A dashboard that optimizes irrigation schedules.',
      student_names: 'Ada Lovelace, Alan Turing',
      is_presenting: true,
      track: 1,
      presentation_order: 3,
    },
    {
      id: 'project-e2e-2',
      semester_label: '2025 Spring',
      class_code: 'ME 140',
      team_number: '2',
      team_name: 'Team Vortex',
      project_title: 'Low-Cost Wind Turbine',
      organization: 'Globex',
      industry: 'Energy',
      abstract: 'A low-cost residential wind turbine prototype.',
      student_names: 'Grace Hopper, Edsger Dijkstra',
      is_presenting: false,
      track: null,
      presentation_order: null,
    },
  ];
}

export function projectDetail(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: 'project-e2e-1',
    project_title: 'Adaptive Irrigation Dashboard',
    team_name: 'Team Helix',
    team_number: '7',
    organization: 'Acme Corp',
    industry: 'Agriculture',
    abstract: 'A dashboard that optimizes irrigation schedules using live sensor data.',
    student_names: 'Ada Lovelace, Alan Turing',
    class_code: 'CSE 120',
    track: 1,
    presentation_order: 3,
    semester_label: '2025 Fall',
    ...overrides,
  };
}

export function schedulePayload(overrides: Partial<EventSchedulePayload> = {}): EventSchedulePayload {
  return {
    event: {
      id: 'event-e2e',
      name: 'E2E Showcase',
      slug: 'e2e-showcase',
      date: '2026-05-01T18:00:00Z',
      location: 'E2E Hall',
      description: 'End-to-end showcase schedule.',
    },
    show_winners: false,
    grand_winners: [],
    expo: {title: 'Expo', location: 'Lobby', items: []},
    presentations_title: 'Presentations',
    sections: [],
    awards: {title: 'Awards', location: 'Main Stage', items: []},
    projects: [
      {
        id: 'project-e2e-1',
        track: 1,
        order: 3,
        year_semester: '2026 Spring',
        class_code: 'CSE 120',
        team_number: '7',
        team_name: 'Team Helix',
        project_title: 'Adaptive Irrigation Dashboard',
        organization: 'Acme Corp',
        industry: 'Agriculture',
        abstract: 'A dashboard that optimizes irrigation schedules.',
        student_names: 'Ada Lovelace, Alan Turing',
        is_presenting: true,
        tooltip: '',
      },
    ],
    ...overrides,
  };
}

export function cmsAcknowledgementPage(overrides: Partial<CMSPageResponse> = {}): CMSPageResponse {
  return {
    slug: 'acknowledgement',
    route: '/acknowledgement',
    title: 'Partners & Sponsors',
    page_css_class: '',
    page_css: '',
    meta_description: '',
    blocks: [
      {
        block_type: 'sponsor_year',
        sort_order: 0,
        data: {
          year: '2025',
          sponsors: [{name: 'Acme Corp', logo_url: ''}],
        },
      },
    ],
    ...overrides,
  };
}
