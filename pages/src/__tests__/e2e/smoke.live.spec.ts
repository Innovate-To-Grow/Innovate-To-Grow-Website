// LIVE-backend smoke layer — no API mocking. Exercises real readiness/CORS,
// the Django admin login page, and that the public SPA route shells render
// without a 5xx against a freshly-migrated (empty) database. Runs on the
// desktop projects only (untagged → excluded from the mobile `@core` grep).
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

test('project and schedule route shells load without server errors', async ({page}) => {
  await expectAppDocument(page, '/current-projects');
  await expectAppDocument(page, '/schedule');
});
