// /account dashboard (seeded auth): renders, edits the profile (PATCH), and
// guards when logged out. Sign-out + cross-root flip is covered in
// cross-root-sync.spec.ts.
import {test, expect} from './fixtures';
import {seedAuthenticatedSession} from './helpers';

test('account dashboard renders the member profile', {tag: '@core'}, async ({page}) => {
  const email = 'account@example.com';
  await seedAuthenticatedSession(page, {
    user: {email},
    profile: {first_name: 'Ada', last_name: 'Lovelace', organization: 'Acme Corp', email},
  });

  await page.goto('/account', {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {name: 'Account Dashboard'})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Profile Information'})).toBeVisible();
  await expect(page.locator('.account-page')).toContainText(email);
});

test('editing the profile sends a PATCH', async ({page}) => {
  const {patchPayloads} = await seedAuthenticatedSession(page, {
    profile: {first_name: 'Ada', last_name: 'Lovelace', organization: 'Acme Corp'},
  });

  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: 'Edit Profile'}).click();
  await page.locator('#account-first-name').fill('Adabelle');
  await page.getByRole('button', {name: 'Save Profile'}).click();

  await expect.poll(() => patchPayloads.length).toBeGreaterThan(0);
  expect((patchPayloads[0] as Record<string, unknown>).first_name).toBe('Adabelle');
});

test('/account redirects to /login when logged out', async ({page}) => {
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});
