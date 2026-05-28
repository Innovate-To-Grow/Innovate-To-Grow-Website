import {expect, test, type Page} from '@playwright/test';

const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function expectAppDocument(page: Page, path: string) {
  const response = await page.goto(path, {waitUntil: 'domcontentloaded'});
  expect(response, `${path} returned a document response`).not.toBeNull();
  expect(response?.status(), `${path} should not return a server error`).toBeLessThan(500);
  await expect(page.locator('body')).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/Traceback|Internal Server Error/i);
}

test('backend readiness and admin login smoke', async ({page, request}) => {
  const readiness = await request.get(`${apiBaseUrl}/readyz/`, {
    headers: {
      Origin: 'http://127.0.0.1:4173',
    },
  });

  expect(readiness.ok()).toBeTruthy();
  await expect.poll(async () => (await readiness.json()).status).toMatch(/^(ok|maintenance)$/);
  expect(readiness.headers()['access-control-allow-origin']).toBe('http://127.0.0.1:4173');

  const adminResponse = await page.goto(`${apiBaseUrl}/admin/login/`, {waitUntil: 'domcontentloaded'});
  expect(adminResponse?.status()).toBeLessThan(500);
  await expect(page.locator('.login-title, h1, [role="heading"]').first()).toBeVisible();
});

test('public frontend routes load homepage, CMS, and news shells', async ({page}) => {
  await expectAppDocument(page, '/');
  await expectAppDocument(page, '/about');
  await expectAppDocument(page, '/news');
  await expectAppDocument(page, '/news/ci-smoke');
});

test('email-code auth route advances from login to verification', async ({page}) => {
  await page.route('**/authn/email-auth/request-code/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({message: 'Verification code sent.'}),
    });
  });

  await expectAppDocument(page, '/login');
  await page.getByLabel('Email').fill('ci-login@example.com');
  await page.getByRole('button', {name: /continue with email/i}).click();
  await expect(page).toHaveURL(/\/verify-email\?flow=auth&email=ci-login%40example\.com/);
});

test('event registration email-code path reaches verification step', async ({page}) => {
  await page.route('**/event/registration-options/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'ci-event',
        name: 'CI Smoke Event',
        slug: 'ci-smoke-event',
        date: '2026-01-01T18:00:00Z',
        location: 'CI Hall',
        description: 'Smoke test event.',
        allow_secondary_email: false,
        collect_phone: false,
        verify_phone: false,
        tickets: [{id: 'ci-ticket', name: 'General Admission'}],
        questions: [],
        registration: null,
        member_emails: [],
        member_profile: null,
        member_phone: null,
        phone_regions: [{code: '1-US', label: 'United States'}],
      }),
    });
  });

  await page.route('**/authn/email-auth/request-code/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({message: 'Verification code sent.'}),
    });
  });

  await expectAppDocument(page, '/event-registration');
  await expect(page.getByRole('heading', {name: 'Event Registration'})).toBeVisible();
  await page.getByLabel('Email').fill('ci-event@example.com');
  await page.getByRole('button', {name: /continue with email/i}).click();
  await expect(page.getByLabel('Verification Code')).toBeVisible();
});
