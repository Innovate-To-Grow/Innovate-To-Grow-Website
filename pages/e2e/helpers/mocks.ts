// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {
  EmailAuthVerifyResponse,
  LoginResponse,
} from '../../src/features/auth/api/types';
import type {EventRegistrationOptions, Registration} from '../../src/features/events/api';
import type {NewsArticle, PaginatedResponse} from '../../src/features/news/api';
import type {PastProjectShare, ProjectDetail, ProjectTableRow} from '../../src/features/projects/api';
import type {CMSPageResponse} from '../../src/features/cms/api';
import type {EventSchedulePayload} from '../../src/features/events/api';
import {loginResponse, newsList, registration as buildRegistration, registrationOptions} from './factories';

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
  opts: {options?: EventRegistrationOptions; registration?: Registration} = {},
): Promise<EventRegistrationMockResult> {
  const created: unknown[] = [];

  await page.route('**/event/registration-options/', (route) =>
    route.fulfill(json(opts.options ?? registrationOptions())),
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
  await page.route(`**/cms/pages/${slug}/`, (route) => route.fulfill(json(response)));
}
