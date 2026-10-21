// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {EmailAuthVerifyResponse, LoginResponse} from '../../../src/features/auth/api/types';
import {loginResponse} from '../factories';
import {mockAuthenticatedLogin} from '../auth';
import {json} from './json';

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

export interface LoginCodeMockResult {
  requestPayloads: unknown[];
  verifyPayloads: unknown[];
}

// Login-code twin of mockEmailAuthFlow: the existing-accounts-only code flow
// (`/authn/login/*`), which answers every address with the same generic
// acknowledgement and never creates an account. Same option semantics.
export async function mockLoginCodeFlow(
  page: Page,
  opts: {verifyResponse?: LoginResponse; verifyStatus?: number} = {},
): Promise<LoginCodeMockResult> {
  const requestPayloads: unknown[] = [];
  const verifyPayloads: unknown[] = [];
  const verifyResponse = opts.verifyResponse ?? loginResponse();
  const verifyStatus = opts.verifyStatus ?? 200;

  if (verifyStatus < 400) {
    await mockAuthenticatedLogin(page, verifyResponse);
  }

  await mockSendVerification(page);

  await page.route('**/authn/login/request-code/', async (route) => {
    requestPayloads.push(route.request().postDataJSON());
    await route.fulfill(
      json({message: 'If an eligible account exists, a verification code has been sent.'}, 202),
    );
  });

  await page.route('**/authn/login/verify-code/', async (route) => {
    verifyPayloads.push(route.request().postDataJSON());
    if (verifyStatus >= 400) {
      await route.fulfill(json({detail: 'Verification code is invalid or has expired.'}, verifyStatus));
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

