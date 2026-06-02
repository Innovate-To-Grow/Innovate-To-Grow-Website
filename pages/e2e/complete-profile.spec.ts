// /complete-profile is guarded inside the component (needs auth + the
// profile-completion flag). Seeding installs the session before navigation.
import {test, expect} from './fixtures';
import {seedAuthenticatedSession} from './helpers';

test('completes the profile and lands on the account dashboard', {tag: '@core'}, async ({page}) => {
  const {patchPayloads} = await seedAuthenticatedSession(page, {
    requiresProfileCompletion: true,
    profile: {first_name: '', last_name: '', organization: ''},
  });

  await page.goto('/complete-profile', {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {name: 'Complete Your Profile'})).toBeVisible();
  await page.getByLabel('First Name').fill('Ada');
  await page.getByLabel('Last Name').fill('Lovelace');
  await page.getByPlaceholder('Company or organization name').fill('Acme Corp');
  await page.getByRole('button', {name: 'Continue to Account'}).click();

  await expect(page).toHaveURL(/\/account$/);
  expect(patchPayloads[0]).toEqual({
    first_name: 'Ada',
    middle_name: '',
    last_name: 'Lovelace',
    organization: 'Acme Corp',
    title: '',
  });
});

test('redirects to /account when no completion is required', async ({page}) => {
  await seedAuthenticatedSession(page);
  await page.goto('/complete-profile', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/account$/);
});

test('redirects to /login when logged out', async ({page}) => {
  await page.goto('/complete-profile', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});
