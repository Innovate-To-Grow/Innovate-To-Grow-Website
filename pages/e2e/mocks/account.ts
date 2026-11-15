// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {Registration} from '../../src/features/events/api';
import {mockSendVerification} from './authFlows';
import {json} from './json';

// -- account emails ----------------------------------------------------------

export async function mockAccountEmails(
  page: Page,
  emails: string[] = ['member@example.com'],
): Promise<void> {
  await page.route('**/authn/account-emails/', (route) =>
    route.fulfill(json({emails})),
  );
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
