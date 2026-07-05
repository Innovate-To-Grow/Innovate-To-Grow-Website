// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {
  ContactEmail,
  ContactPhone,
  EmailAuthVerifyResponse,
  LoginResponse,
} from '../../src/features/auth/api/types';
import type {EventRegistrationOptions, EventRegistrationSummary, Registration} from '../../src/features/events/api';
import type {NewsArticle, PaginatedResponse} from '../../src/features/news/api';
import type {
  PastProjectAISearchResponse,
  PastProjectShare,
  PastProjectShareSummary,
  ProjectDetail,
  ProjectTableRow,
} from '../../src/features/projects/api';
import type {CMSEmbedResponse, CMSPageResponse} from '../../src/features/cms/api';
import type {EventSchedulePayload} from '../../src/features/events/api';
import type {
  AssistantChatSuccessBody,
  AssistantChatUnavailableBody,
  AssistantConfig,
} from '../../src/features/assistant/api';
import {
  loginResponse,
  newsList,
  registration as buildRegistration,
  registrationEvent,
  registrationOptions,
} from './factories';

function json(body: unknown, status = 200) {
  return {status, contentType: 'application/json', body: JSON.stringify(body)};
}

export interface EmailAuthMockResult {
  requestPayloads: unknown[];
  verifyPayloads: unknown[];
}

export async function mockEmailAuthFlow(
  page: Page,
  opts: {verifyResponse?: LoginResponse | EmailAuthVerifyResponse; verifyStatus?: number} = {},
): Promise<EmailAuthMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];

  await page.route('**/authn/email-auth/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Verification code sent.'}));
  });

  await page.route('**/authn/email-auth/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    const status = opts.verifyStatus ?? 200;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Invalid or expired code.'}, status));
      return;
    }
    await route.fulfill(json(opts.verifyResponse ?? loginResponse()));
  });

  return {requestPayloads, verifyPayloads};
}

export interface PhoneAuthMockResult {
  requestPayloads: unknown[];
  verifyPayloads: unknown[];
}

// Phone-auth twin of mockEmailAuthFlow: stubs the SMS request + verify endpoints
// and captures their payloads. On verifyStatus >= 400 it returns the same generic
// invalid-code detail the backend uses (no enumeration leak).
export async function mockPhoneAuthFlow(
  page: Page,
  opts: {verifyResponse?: LoginResponse | EmailAuthVerifyResponse; verifyStatus?: number} = {},
): Promise<PhoneAuthMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];

  await page.route('**/authn/phone-auth/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Verification code sent.'}));
  });

  await page.route('**/authn/phone-auth/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    const status = opts.verifyStatus ?? 200;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Verification code is invalid or has expired.'}, status));
      return;
    }
    await route.fulfill(json(opts.verifyResponse ?? loginResponse()));
  });

  return {requestPayloads, verifyPayloads};
}

export interface PasswordResetMockResult {
  requestPayloads: unknown[];
  verifyPayloads: unknown[];
  confirmPayloads: unknown[];
}

export async function mockPasswordResetFlow(
  page: Page,
  opts: {verifyToken?: string; confirmMessage?: string} = {},
): Promise<PasswordResetMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];
  const confirmPayloads: unknown[] = [];

  await page.route('**/authn/password-reset/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Reset code sent.'}));
  });

  await page.route('**/authn/password-reset/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    await route.fulfill(
      json({message: 'Code verified.', verification_token: opts.verifyToken ?? 'reset-token-e2e'}),
    );
  });

  await page.route('**/authn/password-reset/confirm/', async (route) => {
    confirmPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: opts.confirmMessage ?? 'Password reset successful.'}));
  });

  return {requestPayloads, verifyPayloads, confirmPayloads};
}

export interface EventRegistrationMockResult {
  created: unknown[];
}

export async function mockEventRegistration(
  page: Page,
  opts: {events?: EventRegistrationSummary[]; options?: EventRegistrationOptions; registration?: Registration} = {},
): Promise<EventRegistrationMockResult> {
  const created: unknown[] = [];
  const options = opts.options ?? registrationOptions();

  await page.route('**/event/registration-options/**', (route) =>
    route.fulfill(json(options)),
  );
  await page.route('**/event/registration-events/', (route) =>
    route.fulfill(json(opts.events ?? [registrationEvent({
      id: options.id,
      name: options.name,
      slug: options.slug,
      date: options.date,
      location: options.location,
      description: options.description,
      registration: options.registration,
    })])),
  );

  await page.route('**/event/registrations/', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    created.push(route.request().postDataJSON());
    await route.fulfill(json(opts.registration ?? buildRegistration(), 201));
  });

  await page.route('**/event/send-phone-code/', (route) =>
    route.fulfill(json({detail: 'Code sent.', phone: '+15551234567'})),
  );
  await page.route('**/event/verify-phone-code/', (route) =>
    route.fulfill(json({detail: 'Verified.', verified: true, phone: '+15551234567'})),
  );
  await page.route('**/event/my-tickets/*/resend-email/', (route) =>
    route.fulfill(json({message: 'Email sent successfully.'})),
  );

  return {created};
}

export async function mockNews(
  page: Page,
  opts: {
    listByPage?: Record<number, PaginatedResponse<NewsArticle>>;
    list?: PaginatedResponse<NewsArticle>;
    detail?: NewsArticle;
    detailStatus?: number;
  } = {},
): Promise<void> {
  await page.route(/\/news\//, async (route) => {
    // The SPA route /news/:id also contains "/news/"; never intercept the
    // top-level document navigation, only the data fetches.
    if (route.request().resourceType() === 'document') {
      await route.fallback();
      return;
    }
    const url = new URL(route.request().url());
    const detailMatch = url.pathname.match(/\/news\/([^/]+)\/?$/);
    if (detailMatch && detailMatch[1]) {
      const status = opts.detailStatus ?? 200;
      if (status >= 400) {
        await route.fulfill(json({detail: 'Not found.'}, status));
        return;
      }
      await route.fulfill(json(opts.detail ?? {...newsList().results[0], content: '<p>Full article body.</p>'}));
      return;
    }
    const page_ = Number(url.searchParams.get('page') ?? '1');
    const payload = opts.listByPage?.[page_] ?? opts.list ?? newsList({page: page_});
    await route.fulfill(json(payload));
  });
}

export async function mockSchedule(page: Page, payload: EventSchedulePayload): Promise<void> {
  await page.route(/\/event\/schedule\//, (route) => route.fulfill(json(payload)));
}

export async function mockPastProjects(page: Page, rows: ProjectTableRow[]): Promise<void> {
  await page.route('**/projects/past-all/', (route) => route.fulfill(json(rows)));
}

export async function mockPastProjectShare(page: Page, share: PastProjectShare): Promise<void> {
  // Covers GET (view) and PATCH/PUT (owner edit): the update echoes the merged share back.
  // RegExp (not a glob) so it matches the trailing-slash detail URL `.../past-shares/<id>/`.
  await page.route(/\/projects\/past-shares\/[^/]+\/?(\?.*)?$/, (route) => {
    const method = route.request().method();
    if (method === 'PATCH' || method === 'PUT') {
      const body = (route.request().postDataJSON() ?? {}) as Partial<PastProjectShare>;
      route.fulfill(json({...share, ...body}));
      return;
    }
    route.fulfill(json(share));
  });
}

export async function mockProjectDetail(
  page: Page,
  detail: ProjectDetail,
  opts: {status?: number} = {},
): Promise<void> {
  await page.route(`**/projects/${detail.id}/`, (route) => {
    if (opts.status && opts.status >= 400) {
      route.fulfill(json({detail: 'Not found.'}, opts.status));
      return;
    }
    route.fulfill(json(detail));
  });
}

export async function mockCmsPage(
  page: Page,
  slug: string,
  response: CMSPageResponse,
): Promise<void> {
  // Empty slug = homepage, whose URL is …/cms/pages/ with no trailing segment.
  // Use a regex so it does not also match …/cms/pages/about/.
  if (!slug) {
    await page.route(/\/cms\/pages\/$/, (route) => route.fulfill(json(response)));
    return;
  }
  await page.route(`**/cms/pages/${slug}/`, (route) => route.fulfill(json(response)));
}

// -- assistant ---------------------------------------------------------------

export async function mockAssistantConfig(
  page: Page,
  config?: AssistantConfig,
): Promise<void> {
  await page.route('**/assistant/config/', (route) =>
    route.fulfill(json(config ?? {enabled: true, welcome_message: 'Hi!', starter_questions: [], unavailable_message: 'Down.', max_message_chars: 2000})),
  );
}

export interface AssistantChatMockResult {
  messages: unknown[];
}

export async function mockAssistantChat(
  page: Page,
  opts: {
    successResponse?: AssistantChatSuccessBody;
    unavailableResponse?: AssistantChatUnavailableBody;
    /** Force 429 budget error. */
    budgetError?: boolean;
    /** Force 500 network error. */
    networkError?: boolean;
  } = {},
): Promise<AssistantChatMockResult> {
  const messages: unknown[] = [];

  await page.route('**/assistant/chat/', async (route) => {
    messages.push(route.request().postDataJSON());
    if (opts.networkError) {
      await route.abort('failed');
      return;
    }
    if (opts.budgetError) {
      await route.fulfill(json({detail: 'Budget exceeded.'}, 429));
      return;
    }
    if (opts.unavailableResponse) {
      await route.fulfill(json(opts.unavailableResponse));
      return;
    }
    await route.fulfill(
      json(
        opts.successResponse ?? {
          available: true,
          reply: 'Here is the answer to your question.',
          usage: {inputTokens: 10, outputTokens: 5, totalTokens: 15},
        },
      ),
    );
  });

  return {messages};
}

// -- CMS embed ---------------------------------------------------------------

export async function mockCmsEmbed(
  page: Page,
  embedSlug: string,
  response: CMSEmbedResponse,
): Promise<void> {
  await page.route(`**/cms/embed/${embedSlug}/`, (route) => route.fulfill(json(response)));
}

// -- AI search ---------------------------------------------------------------

export interface AiSearchMockResult {
  queries: unknown[];
}

export async function mockAiSearch(
  page: Page,
  opts: {
    response?: PastProjectAISearchResponse;
    /** Return 401 for unauthenticated tests. */
    status?: number;
  } = {},
): Promise<AiSearchMockResult> {
  const queries: unknown[] = [];

  await page.route('**/projects/past-ai-search/', async (route) => {
    queries.push(route.request().postDataJSON());
    const status = opts.status ?? 200;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Unauthorized.'}, status));
      return;
    }
    await route.fulfill(
      json(
        opts.response ?? {
          available: true,
          query: '',
          results: [],
        },
      ),
    );
  });

  return {queries};
}

// -- past project shares CRUD ------------------------------------------------

export interface PastProjectShareCreateMockResult {
  created: unknown[];
}

export async function mockPastProjectShareCreate(
  page: Page,
  opts: {response?: PastProjectShare} = {},
): Promise<PastProjectShareCreateMockResult> {
  const created: unknown[] = [];

  await page.route('**/projects/past-shares/', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    created.push(route.request().postDataJSON());
    await route.fulfill(
      json(
        opts.response ?? {
          id: 'share-new',
          name: 'New Share',
          rows: [],
          note: '',
          details_text: '',
          share_url: '/past-projects/share-new',
          can_edit: true,
          created_at: new Date().toISOString(),
        },
        201,
      ),
    );
  });

  return {created};
}

export async function mockPastProjectSharesList(
  page: Page,
  shares: PastProjectShareSummary[] = [],
): Promise<void> {
  await page.route('**/projects/past-shares/mine/', (route) =>
    route.fulfill(json(shares)),
  );
}

export async function mockPastProjectShareDelete(
  page: Page,
  id: string,
): Promise<void> {
  await page.route(`**/projects/past-shares/${id}/`, async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });
}

// -- account emails ----------------------------------------------------------

export async function mockAccountEmails(
  page: Page,
  emails: string[] = ['member@example.com'],
): Promise<void> {
  await page.route('**/authn/account-emails/', (route) =>
    route.fulfill(json({emails})),
  );
}

// -- contact emails CRUD -----------------------------------------------------

export interface ContactEmailsMockResult {
  created: unknown[];
  updated: unknown[];
  deleted: string[];
  primaryPayloads: unknown[];
}

export async function mockContactEmailsCRUD(
  page: Page,
  opts: {initial?: ContactEmail[]} = {},
): Promise<ContactEmailsMockResult> {
  const emails: ContactEmail[] = opts.initial ?? [];
  const created: unknown[] = [];
  const updated: unknown[] = [];
  const deleted: string[] = [];
  const primaryPayloads: unknown[] = [];

  // GET list
  await page.route('**/authn/contact-emails/', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill(json(emails));
      return;
    }
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      created.push(body);
      const newEmail: ContactEmail = {
        id: `cemail-${Date.now()}`,
        email_address: (body.email_address as string) ?? 'new@example.com',
        email_type: (body.email_type as ContactEmail['email_type']) ?? 'secondary',
        subscribe: (body.subscribe as boolean) ?? false,
        verified: false,
        created_at: new Date().toISOString(),
      };
      emails.push(newEmail);
      await route.fulfill(json(newEmail, 201));
      return;
    }
    await route.fulfill(json({detail: 'Method not allowed.'}, 405));
  });

  // Detail routes: PATCH, DELETE, make-primary, request-verification, verify-code
  await page.route(/\/authn\/contact-emails\/[^/]+\/.*$/, async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.replace(/\/$/, '').split('/');
    const id = parts[parts.length - 2]; // contact-emails/{id}/make-primary/
    const action = parts[parts.length - 1];

    if (action === 'make-primary') {
      primaryPayloads.push({id});
      await route.fulfill(json({message: 'Primary email updated.'}));
      return;
    }
    if (action === 'request-verification') {
      await route.fulfill(json({message: 'Verification code sent.'}));
      return;
    }
    if (action === 'verify-code') {
      await route.fulfill(json({message: 'Email verified.'}));
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  await page.route(/\/authn\/contact-emails\/[^/]+\/?$/, async (route) => {
    const url = new URL(route.request().url());
    const id = url.pathname.replace(/\/$/, '').split('/').pop() ?? '';
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      updated.push({id, ...body});
      await route.fulfill(json({message: 'Updated.'}));
      return;
    }
    if (route.request().method() === 'DELETE') {
      deleted.push(id);
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  return {created, updated, deleted, primaryPayloads};
}

// -- contact phones CRUD -----------------------------------------------------

export interface ContactPhonesMockResult {
  created: unknown[];
  updated: unknown[];
  deleted: string[];
}

export async function mockContactPhonesCRUD(
  page: Page,
  opts: {initial?: ContactPhone[]} = {},
): Promise<ContactPhonesMockResult> {
  const phones: ContactPhone[] = opts.initial ?? [];
  const created: unknown[] = [];
  const updated: unknown[] = [];
  const deleted: string[] = [];

  await page.route('**/authn/contact-phones/', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill(json(phones));
      return;
    }
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      created.push(body);
      const newPhone: ContactPhone = {
        id: `cphone-${Date.now()}`,
        phone_number: (body.phone_number as string) ?? '+12065551234',
        region: (body.region as string) ?? '1-US',
        region_display: 'United States',
        subscribe: (body.subscribe as boolean) ?? false,
        verified: false,
        created_at: new Date().toISOString(),
      };
      phones.push(newPhone);
      await route.fulfill(json(newPhone, 201));
      return;
    }
    await route.fulfill(json({detail: 'Method not allowed.'}, 405));
  });

  // Detail routes: PATCH, DELETE, request-verification, verify-code
  await page.route(/\/authn\/contact-phones\/[^/]+\/.*$/, async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.replace(/\/$/, '').split('/');
    const action = parts[parts.length - 1];

    if (action === 'request-verification') {
      await route.fulfill(json({message: 'Verification code sent.'}));
      return;
    }
    if (action === 'verify-code') {
      await route.fulfill(json({message: 'Phone verified.'}));
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  await page.route(/\/authn\/contact-phones\/[^/]+\/?$/, async (route) => {
    const url = new URL(route.request().url());
    const id = url.pathname.replace(/\/$/, '').split('/').pop() ?? '';
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      updated.push({id, ...body});
      await route.fulfill(json({message: 'Updated.'}));
      return;
    }
    if (route.request().method() === 'DELETE') {
      deleted.push(id);
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  return {created, updated, deleted};
}

// -- password change flow ----------------------------------------------------

export interface PasswordChangeMockResult {
  requestPayloads: unknown[];
  verifyPayloads: unknown[];
  confirmPayloads: unknown[];
}

export async function mockPasswordChangeFlow(
  page: Page,
  opts: {verifyToken?: string} = {},
): Promise<PasswordChangeMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];
  const confirmPayloads: unknown[] = [];

  await page.route('**/authn/change-password/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Code sent.', channel: 'email', destination: 'm***@example.com'}));
  });

  await page.route('**/authn/change-password/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    await route.fulfill(
      json({message: 'Code verified.', verification_token: opts.verifyToken ?? 'change-token-e2e'}),
    );
  });

  await page.route('**/authn/change-password/confirm/', async (route) => {
    confirmPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Password changed successfully.'}));
  });

  return {requestPayloads, verifyPayloads, confirmPayloads};
}

// -- account delete flow -----------------------------------------------------

export interface AccountDeleteMockResult {
  requestPayloads: unknown[];
  verifyPayloads: unknown[];
  confirmPayloads: unknown[];
}

export async function mockAccountDeleteFlow(
  page: Page,
  opts: {verifyToken?: string} = {},
): Promise<AccountDeleteMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];
  const confirmPayloads: unknown[] = [];

  await page.route('**/authn/delete-account/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Deletion code sent.'}));
  });

  await page.route('**/authn/delete-account/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    await route.fulfill(
      json({message: 'Code verified.', verification_token: opts.verifyToken ?? 'delete-token-e2e'}),
    );
  });

  await page.route('**/authn/delete-account/confirm/', async (route) => {
    confirmPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Account deleted successfully.'}));
  });

  return {requestPayloads, verifyPayloads, confirmPayloads};
}

// -- password login ----------------------------------------------------------

export interface PasswordLoginMockResult {
  loginPayloads: unknown[];
}

export async function mockPasswordLogin(
  page: Page,
  opts: {
    response?: LoginResponse;
    status?: number;
  } = {},
): Promise<PasswordLoginMockResult> {
  const loginPayloads: unknown[] = [];

  await page.route('**/authn/login/', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    loginPayloads.push(route.request().postDataJSON());
    const status = opts.status ?? 200;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Invalid credentials.'}, status));
      return;
    }
    await route.fulfill(json(opts.response ?? loginResponse()));
  });

  return {loginPayloads};
}

// -- my tickets --------------------------------------------------------------

export async function mockMyTickets(
  page: Page,
  tickets: Registration[] = [],
): Promise<void> {
  await page.route('**/event/my-tickets/', (route) =>
    route.fulfill(json(tickets)),
  );
}

// -- ticket resend -----------------------------------------------------------

export interface TicketResendMockResult {
  resendPayloads: string[];
}

export async function mockTicketResend(
  page: Page,
): Promise<TicketResendMockResult> {
  const resendPayloads: string[] = [];

  await page.route(/\/event\/my-tickets\/[^/]+\/resend-email\//, async (route) => {
    const url = new URL(route.request().url());
    const ticketId = url.pathname.replace(/\/$/, '').split('/').slice(-3, -1)[0] ?? '';
    resendPayloads.push(ticketId);
    await route.fulfill(json({message: 'Email sent successfully.'}));
  });

  return {resendPayloads};
}
