import {readFile} from 'node:fs/promises';
import {createChallenge, pbkdf2, verifySolution, type Challenge, type Payload} from 'altcha/lib';
import type {Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';

const secret = 'local-browser-regression-secret';
const challengeId = '11111111-1111-4111-8111-111111111111';

async function challengeFixture(): Promise<Challenge> {
  return createChallenge({algorithm: 'PBKDF2/SHA-256', cost: 1, counter: 4, deriveKey: pbkdf2.deriveKey, hmacSignatureSecret: secret});
}

async function installChallenge(page: Page, challenge: Challenge) {
  await page.route('**/authn/send-verification/challenge/', (route) => route.fulfill({json: {
    challenge_id: challengeId, expires_at: new Date(Date.now() + 300_000).toISOString(),
    algorithm: challenge.parameters.algorithm, cost: 1, challenge,
  }}));
}

async function beginEmailSend(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill('widget@example.com');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
}

async function assertProof(payload: string, challenge: Challenge) {
  const decoded = JSON.parse(Buffer.from(payload, 'base64').toString()) as Payload;
  const verified = await verifySolution({challenge, solution: decoded.solution, deriveKey: pbkdf2.deriveKey, hmacSignatureSecret: secret});
  expect(verified.verified).toBe(true);
}

test('real ALTCHA widget initializes, solves, and dispatches a verifiable proof once', async ({page}) => {
  const challenge = await challengeFixture();
  await installChallenge(page, challenge);
  const sends: Record<string, string>[] = [];
  await page.route('**/authn/email-auth/request-code/', (route) => {
    sends.push(route.request().postDataJSON());
    return route.fulfill({status: 202, json: {message: 'Verification code sent.'}});
  });
  await beginEmailSend(page);
  await expect(page).toHaveURL(/\/verify-email\?flow=auth/);
  expect(sends).toHaveLength(1);
  expect(sends[0].verification_challenge_id).toBe(challengeId);
  expect(sends[0].send_request_id).toMatch(/^[0-9a-f-]{36}$/);
  await assertProof(sends[0].verification_payload, challenge);
  await expect(page.locator('altcha-widget')).toHaveCount(0);
});

test('a real widget failure returns promptly and never sends', async ({page}) => {
  const challenge = await challengeFixture();
  challenge.parameters.algorithm = 'UNSUPPORTED';
  await installChallenge(page, challenge);
  let sends = 0;
  await page.route('**/authn/email-auth/request-code/', (route) => {sends++; return route.fulfill({json: {}});});
  await beginEmailSend(page);
  await expect(page.locator('.auth-alert.error')).toContainText('Verification failed', {timeout: 5000});
  expect(sends).toBe(0);
  await expect(page.locator('altcha-widget')).toHaveCount(0);
});

test('HTTP unknown survives reload and checks status without sending a second code', async ({page}) => {
  await installChallenge(page, await challengeFixture());
  let sends = 0;
  let lookups = 0;
  await page.route('**/authn/email-auth/request-code/', (route) => {
    sends++;
    return route.fulfill({status: 409, json: {code: 'send_unknown', request_id: route.request().postDataJSON().send_request_id}});
  });
  await page.route('**/authn/send-verification/requests/**', (route) => {
    lookups++;
    return route.fulfill({json: {status: 'unknown', code: 'send_unknown', result: {}, http_status: 409}});
  });
  await beginEmailSend(page);
  await expect(page.locator('.auth-alert.error')).toContainText('still unresolved');
  await beginEmailSend(page);
  await expect(page.locator('.auth-alert.error')).toContainText('still unresolved');
  expect(sends).toBe(1);
  expect(lookups).toBe(2);
});

for (const action of ['request_code', 'remembered_code', 'resend']) {
  test(`admin ${action} uses the configured asset and cookie-scoped route with the real widget`, async ({page, baseURL}) => {
    const challenge = await challengeFixture();
    const wrapper = await readFile(new URL('../../../src/apps/core/static/admin/js/send-verification.js', import.meta.url), 'utf8');
    const widget = await readFile(new URL('../../../src/assets/vendor/altcha/altcha.umd.js', import.meta.url), 'utf8');
    const origin = new URL(baseURL ?? 'http://127.0.0.1:4173').origin;
    await page.context().addCookies([{name: 'i2g_last_admin_member', value: 'signed-test-cookie', domain: new URL(origin).hostname, path: '/admin/'}]);
    let assetLoads = 0;
    await page.route('https://static.example.test/altcha.js', (route) => {
      assetLoads++;
      if (action === 'request_code' && assetLoads === 1) return route.abort('failed');
      return route.fulfill({contentType: 'text/javascript', body: widget});
    });
    await page.route('**/admin-wrapper.js', (route) => route.fulfill({contentType: 'text/javascript', body: wrapper}));
    let challengeCalls = 0;
    await page.route('**/admin/send-verification/challenge/', async (route) => {
      challengeCalls++;
      expect(route.request().postDataJSON().operation).toBe(`admin.login.${action}`);
      expect(await route.request().headerValue('cookie')).toContain('i2g_last_admin_member=signed-test-cookie');
      expect(await route.request().headerValue('x-csrftoken')).toBe('csrf-test-token');
      await route.fulfill({json: {challenge_id: challengeId, challenge}});
    });
    let submitted: URLSearchParams | null = null;
    await page.route('**/admin/login/', async (route) => {
      if (route.request().method() === 'POST') {
        submitted = new URLSearchParams(route.request().postData() ?? '');
        await route.fulfill({contentType: 'text/html', body: '<p>Code sent</p>'});
        return;
      }
      await route.fulfill({contentType: 'text/html', body: `<script src="/admin-wrapper.js" data-session-key="browser-test-session" data-challenge-url="/admin/send-verification/challenge/" data-altcha-url="https://static.example.test/altcha.js"></script><div class="login-box"><form method="post"><input name="csrfmiddlewaretoken" value="csrf-test-token" type="hidden"><input name="action" value="${action}" type="hidden">${action === 'request_code' ? '<input name="email" value="admin@example.com">' : ''}<button type="submit">Send code</button></form></div>`});
    });
    await page.goto(`${origin}/admin/login/`);
    await page.getByRole('button', {name: 'Send code'}).click();
    if (action === 'request_code') {
      await expect(page.locator('.send-verification-status')).toContainText('Unable to load verification assets');
      await page.getByRole('button', {name: 'Send code'}).click();
    }
    await expect(page.getByText('Code sent', {exact: true})).toBeVisible();
    expect(challengeCalls).toBe(action === 'request_code' ? 2 : 1);
    expect(submitted).not.toBeNull();
    await assertProof(submitted!.get('verification_payload')!, challenge);
  });
}

test('admin retains the request across a lost native response and blocks a duplicate send', async ({page, baseURL}) => {
  const challenge = await challengeFixture();
  const wrapper = await readFile(new URL('../../../src/apps/core/static/admin/js/send-verification.js', import.meta.url), 'utf8');
  const widget = await readFile(new URL('../../../src/assets/vendor/altcha/altcha.umd.js', import.meta.url), 'utf8');
  const origin = new URL(baseURL ?? 'http://127.0.0.1:4173').origin;
  const statusPath = '/authn/send-verification/requests/00000000-0000-0000-0000-000000000000/';
  let challenges = 0;
  let sends = 0;
  await page.route('**/admin-wrapper.js', (route) => route.fulfill({contentType: 'text/javascript', body: wrapper}));
  await page.route('https://static.example.test/altcha.js', (route) => route.fulfill({contentType: 'text/javascript', body: widget}));
  await page.route('**/admin/send-verification/challenge/', (route) => {
    challenges++;
    return route.fulfill({json: {challenge_id: challengeId, challenge}});
  });
  await page.route('**/authn/send-verification/requests/**', (route) => route.fulfill({json: {status: 'unknown'}}));
  await page.route('**/admin/login/', (route) => {
    if (route.request().method() === 'POST') {
      sends++;
      return route.abort('failed');
    }
    return route.fulfill({contentType: 'text/html', body: `<script src="/admin-wrapper.js" data-session-key="lost-response-session" data-status-url="${statusPath}" data-challenge-url="/admin/send-verification/challenge/" data-altcha-url="https://static.example.test/altcha.js"></script><div class="login-box"><form method="post"><input name="csrfmiddlewaretoken" value="csrf-test-token" type="hidden"><input name="email" value="admin@example.com"><button type="submit">Send code</button></form></div>`});
  });
  await page.goto(`${origin}/admin/login/`);
  await page.getByRole('button', {name: 'Send code'}).click();
  await expect.poll(() => sends).toBe(1);
  await page.goto(`${origin}/admin/login/`);
  await expect(page.locator('.send-verification-status')).toContainText('still unresolved');
  await page.getByRole('button', {name: 'Send code'}).click();
  await expect(page.locator('.send-verification-status')).toContainText('still unresolved');
  expect(challenges).toBe(1);
  expect(sends).toBe(1);
});
