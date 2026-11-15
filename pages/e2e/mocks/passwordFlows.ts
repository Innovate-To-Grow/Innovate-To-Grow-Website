// Password `page.route` installers: password reset, password sign-in and the RSA public key the password
// forms encrypt with. Same conventions as authFlows.ts.
import type {Page} from '@playwright/test';
import type {LoginResponse} from '../../src/features/auth/api/contracts/types';
import {loginResponse} from '../helpers/factories';
import {mockAuthenticatedLogin} from '../helpers/session';
import {mockSendVerification} from './authFlows';
import {json} from './json';

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

// A real RSA-2048 SPKI public key so the browser's Web Crypto
// `importKey('spki', …, {name:'RSA-OAEP', hash:'SHA-256'})` succeeds for the
// password-confirm flows. Encryption output is never decrypted by the mocks —
// specs assert the request body SHAPE, not the plaintext.
export const MOCK_RSA_PUBLIC_KEY_PEM = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuZH0ooTxP1mSaA+q1cmX
t22LrYF+n5SrQ7uk9mZWKJYrsAFZbC9gAkqRc1+wXa0zRUoaNe26czJyx0BfXSLc
VhTo5uGfIcz3t8gVUz6jG91QCjaBNKzvarbCfvYIXlXlZZEyG8SpCIHxEwTbW46A
cKUHmrW54Chp6eOFkPoZG8hTllI214eitYBqRvp+1WMAJao29zP5GOFwon31rj6s
ALlPDE79H+9x8+QRI+mexhMqg4nGA9iLcMFrJA3y6+Ac+n8hUnIvlp+j1AfAWeKf
A5K7SCSlT4nt8j5SSgwXg0N4xMu/EpWf0UsjpC6KTDo679ANMQTcZUNzwOGz/Wds
FQIDAQAB
-----END PUBLIC KEY-----`;

/** Serve the encryption public key so RSA-OAEP password flows can run. */
export async function mockPublicKey(page: Page): Promise<void> {
  await page.route('**/authn/public-key/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({public_key: MOCK_RSA_PUBLIC_KEY_PEM, key_id: 'e2e-key'}),
    }),
  );
}
