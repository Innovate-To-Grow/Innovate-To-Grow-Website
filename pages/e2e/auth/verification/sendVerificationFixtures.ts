import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createChallenge, pbkdf2, verifySolution, type Challenge, type Payload} from 'altcha/lib';
import type {Page} from '@playwright/test';
import {expect} from '../../helpers/fixtures';

const secret = 'local-browser-regression-secret';
export const challengeId = '11111111-1111-4111-8111-111111111111';
export const execFileAsync = promisify(execFile);

export async function challengeFixture(): Promise<Challenge> {
  return createChallenge({algorithm: 'PBKDF2/SHA-256', cost: 1, counter: 4, deriveKey: pbkdf2.deriveKey, hmacSignatureSecret: secret});
}

export async function installChallenge(page: Page, challenge: Challenge) {
  await page.route('**/authn/send-verification/challenge/', (route) => route.fulfill({json: {
    challenge_id: challengeId, expires_at: new Date(Date.now() + 300_000).toISOString(),
    algorithm: challenge.parameters.algorithm, cost: 1, challenge,
  }}));
}

export async function beginEmailSend(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill('widget@example.com');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
}

export async function assertProof(payload: string, challenge: Challenge) {
  const decoded = JSON.parse(Buffer.from(payload, 'base64').toString()) as Payload;
  const verified = await verifySolution({challenge, solution: decoded.solution, deriveKey: pbkdf2.deriveKey, hmacSignatureSecret: secret});
  expect(verified.verified).toBe(true);
}

export async function countWorkersOnHighCoreDevice(page: Page): Promise<() => number> {
  let workers = 0;
  // The counter lives outside the page so native admin navigation cannot reset it.
  await page.exposeFunction('recordVerificationWorker', () => {workers++;});
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', {configurable: true, get: () => 64});
    window.Worker = new Proxy(window.Worker, {
      construct(target, args, newTarget) {
        const worker = Reflect.construct(target, args, newTarget);
        void (window as typeof window & {recordVerificationWorker: () => Promise<void>}).recordVerificationWorker();
        return worker;
      },
    });
  });
  return () => workers;
}
