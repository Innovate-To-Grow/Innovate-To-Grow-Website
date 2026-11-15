import {randomUUID} from 'node:crypto';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {test, expect} from '../../helpers/fixtures';
import {
  assertProof,
  beginEmailSend,
  challengeFixture,
  challengeId,
  countWorkersOnHighCoreDevice,
  execFileAsync,
  installChallenge,
} from './sendVerificationFixtures';

test('real ALTCHA widget bounds workers on high-core devices and dispatches a verifiable proof once', async ({page}) => {
  const workers = await countWorkersOnHighCoreDevice(page);
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
  await expect.poll(workers).toBe(1);
  await expect(page.locator('altcha-widget')).toHaveCount(0);
});

test('Python-issued ALTCHA challenge is solved by the browser widget and verified by Python', async ({page}) => {
  const email = `altcha-cross-language-${randomUUID()}@example.test`;
  const issued = page.waitForResponse((response) =>
    response.url().endsWith('/authn/send-verification/challenge/') && response.request().method() === 'POST');
  const sends: Record<string, string>[] = [];
  await page.route('**/authn/email-auth/request-code/', (route) => {
    sends.push(route.request().postDataJSON());
    return route.fulfill({status: 202, json: {message: 'Verification code sent.'}});
  });

  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  const challengeResponse = await issued;
  expect(challengeResponse.status()).toBe(200);
  const challenge = await challengeResponse.json() as {challenge_id: string};
  await expect(page).toHaveURL(/\/verify-email\?flow=auth/);
  expect(sends).toHaveLength(1);
  expect(sends[0].verification_challenge_id).toBe(challenge.challenge_id);

  const backendDir = fileURLToPath(new URL('../../../../src/', import.meta.url));
  const python = process.env.ALTCHA_TEST_PYTHON ?? join(backendDir, '.venv/bin/python');
  const verify = [
    'import django, sys',
    'django.setup()',
    'from apps.authn.services.send_verification.rules.config import load_settings',
    'from apps.authn.services.send_verification.proofs import verify_payload',
    'verify_payload(sys.argv[1], load_settings())',
  ].join('\n');
  await execFileAsync(python, ['-c', verify, sends[0].verification_payload], {
    cwd: backendDir,
    env: {...process.env, DJANGO_SETTINGS_MODULE: 'config.settings.environments.test'},
  });
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
