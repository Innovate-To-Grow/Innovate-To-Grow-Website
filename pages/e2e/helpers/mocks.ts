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
import {mockAuthenticatedLogin} from './auth';

function json(body: unknown, status = 200) {
  return {status, contentType: 'application/json', body: JSON.stringify(body)};
}

export async function mockSendVerification(page: Page): Promise<void> {
  await page.route('**/authn/send-verification/challenge/', async (route) => {
    await route.fulfill(
      json({
        challenge_id: '11111111-1111-4111-8111-111111111111',
        expires_at: new Date(Date.now() + 300000).toISOString(),
        algorithm: 'PBKDF2/SHA-256',
        cost: 1,
        challenge: {parameters: {
          algorithm: 'PBKDF2/SHA-256', cost: 1, keyLength: 32, keyPrefix: '00',
          nonce: 'cea3887d17e708f96ba9b276b28f1637', salt: '61562030d20d368221f28e886c0de709',
        }},
      }),
    );
  });
  await page.route('**/authn/send-verification/requests/**', async (route) => {
    await route.fulfill(
      json({
        request_id: '22222222-2222-4222-8222-222222222222',
        status: 'provider_accepted',
        code: null,
        result: {message: 'Verification code sent.'},
        challenge_id: null,
      }),
    );
  });
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
  const verifyResponse = opts.verifyResponse ?? loginResponse();
  const verifyStatus = opts.verifyStatus ?? 200;

  if (verifyStatus < 400) {
    await mockAuthenticatedLogin(page, verifyResponse);
  }

  await mockSendVerification(page);

  await page.route('**/authn/email-auth/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(json({message: 'Verification code sent.'}));
  });

  await page.route('**/authn/email-auth/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    const status = verifyStatus;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Invalid or expired code.'}, status));
      return;
    }
    await mockAuthenticatedLogin(page, verifyResponse);
    await route.fulfill(json(verifyResponse));
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
  const challengeId = 'a9a1d853-9687-4199-9f25-d93509e408aa';
  const verifyResponse = opts.verifyResponse ?? loginResponse();
  const verifyStatus = opts.verifyStatus ?? 200;

  if (verifyStatus < 400) {
    await mockAuthenticatedLogin(page, verifyResponse);
  }

  await mockSendVerification(page);

  await page.route('**/authn/phone-auth/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(
      json({
        message: 'Verification code sent.',
        challenge_id: challengeId,
      }),
    );
  });

  await page.route('**/authn/phone-auth/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    const status = verifyStatus;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Verification code is invalid or has expired.'}, status));
      return;
    }
    await mockAuthenticatedLogin(page, verifyResponse);
    await route.fulfill(json(verifyResponse));
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
  opts: {
    requestChallengeId?: string;
    verifyToken?: string;
    confirmMessage?: string;
  } = {},
): Promise<PasswordResetMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];
  const confirmPayloads: unknown[] = [];

  await mockSendVerification(page);

  await page.route('**/authn/password-reset/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(
      json({
        message: 'Reset code sent.',
        ...(opts.requestChallengeId
          ? {challenge_id: opts.requestChallengeId}
          : {}),
      }),
    );
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

  await mockSendVerification(page);

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

export interface PastProjectShareMockController {
  patchPayloads: Partial<PastProjectShare>[];
  deleted: boolean;
  getCurrent: () => PastProjectShare;
  replaceCurrent: (share: PastProjectShare) => void;
}

export async function mockPastProjectShare(
  page: Page,
  share: PastProjectShare,
): Promise<PastProjectShareMockController> {
  let current = {...share};
  const patchPayloads: Partial<PastProjectShare>[] = [];
  let deleted = false;

  await page.route(/\/projects\/past-shares\/[^/]+\/?(\?.*)?$/, async (route) => {
    const method = route.request().method();
    if (deleted) {
      await route.fulfill(json({detail: 'Not found.'}, 404));
      return;
    }
    if (method === 'PATCH' || method === 'PUT') {
      const body = (route.request().postDataJSON() ?? {}) as Partial<PastProjectShare>;
      patchPayloads.push(body);
      if (body.version !== current.version) {
        await route.fulfill(
          json(
            {
              code: 'stale_snapshot',
              detail: 'This shared project changed.',
              current,
            },
            409,
          ),
        );
        return;
      }
      current = {...current, ...body, version: current.version + 1};
      await route.fulfill(json(current));
      return;
    }
    if (method === 'DELETE') {
      deleted = true;
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json(current));
  });

  return {
    patchPayloads,
    get deleted() {
      return deleted;
    },
    getCurrent: () => ({...current}),
    replaceCurrent: (nextShare) => {
      current = {...nextShare};
    },
  };
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
  // The homepage uses its dedicated published-only endpoint; catch-all CMS
  // routes continue to use the route-specific pages endpoint.
  if (!slug) {
    await page.route('**/cms/homepage/', (route) =>
      route.fulfill(json(response)),
    );
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

  await mockSendVerification(page);

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
      await route.fulfill(
        json({
          message: 'Verification code sent.',
          challenge_id: '87f80894-955d-49d7-b5f3-2aed231087b1',
        }),
      );
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

  await mockSendVerification(page);

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

  await mockSendVerification(page);

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

  await mockSendVerification(page);

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
  const response = opts.response ?? loginResponse();
  const status = opts.status ?? 200;

  if (status < 400) {
    await mockAuthenticatedLogin(page, response);
  }

  await page.route('**/authn/login/', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    loginPayloads.push(route.request().postDataJSON());
    if (status >= 400) {
      await route.fulfill(json({detail: 'Invalid credentials.'}, status));
      return;
    }
    await mockAuthenticatedLogin(page, response);
    await route.fulfill(json(response));
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
