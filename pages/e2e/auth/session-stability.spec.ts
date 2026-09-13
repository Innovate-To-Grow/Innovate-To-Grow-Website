import type {BrowserContext, Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';
import {
  aiSearchResponse,
  expectSignedInAs,
  mintFakeJwt,
  mockHealthyAppShell,
  mockPastProjects,
  pastProjectRows,
  profileResponse,
} from '../helpers';

function watchAccountNavigation(page: Page): string[] {
  const unexpectedPaths: string[] = [];
  let reachedAccount = false;
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame()) return;
    const path = new URL(frame.url()).pathname;
    if (path === '/account') reachedAccount = true;
    else if (reachedAccount) unexpectedPaths.push(path);
  });
  return unexpectedPaths;
}

async function mockStableSession(context: BrowserContext, page: Page) {
  const email = 'two-tabs@example.com';
  const user = {member_uuid: 'member-two-tabs', email, phone: '', is_staff: false};
  // The backend serializes an absent image as null. Omitting the property in
  // both mocks misses the profile/session storage feedback loop.
  const profile = {
    ...profileResponse({...user, first_name: 'Ada', last_name: 'Lovelace', organization: 'Acme Corp'}),
    profile_image: null,
  };
  await context.addInitScript(({user, access}) => {
    // Opening the second tab must reuse the first tab's current session rather
    // than overwrite it with the original fixture on every navigation.
    if (!localStorage.getItem('i2g_auth_session')) {
      localStorage.setItem('i2g_auth_session', JSON.stringify({
        version: 1,
        generation: 'two-tabs-generation',
        access,
        refresh: 'two-tabs-refresh',
        user,
        requires_profile_completion: false,
      }));
    }
  }, {user, access: mintFakeJwt()});

  const requests = new Map<string, number>();
  const unexpectedRequests: string[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await context.route('**/*', async (route) => {
    const request = route.request();
    if (!['fetch', 'xhr'].includes(request.resourceType())) return route.continue();
    // CI calls the backend origin directly; local preview uses the /api proxy.
    const path = new URL(request.url()).pathname.replace(/^\/api(?=\/)/, '');
    const key = `${request.method()} ${path}`;
    requests.set(key, (requests.get(key) ?? 0) + 1);
    let data: unknown;
    if (key === 'GET /authn/session/') {
      await new Promise((resolve) => setTimeout(resolve, 75));
      data = {user: profile, requires_profile_completion: false, next_step: 'account'};
    } else if (key === 'GET /authn/profile/') {
      await new Promise((resolve) => setTimeout(resolve, 50));
      data = profile;
    } else if (key === 'GET /authn/account-emails/') {
      data = {emails: [email]};
    } else if ([
      'GET /authn/contact-emails/',
      'GET /authn/contact-phones/',
      'GET /event/my-tickets/',
      'GET /event/registration-events/',
      'GET /projects/past-shares/mine/',
    ].includes(key)) {
      data = [];
    } else {
      // Do not silently return success (or automatically refresh fake tokens)
      // for a missing API mock: that could hide the cause of an auth failure.
      unexpectedRequests.push(key);
      await route.fulfill({status: 500, json: {detail: `Unexpected request: ${key}`}});
      return;
    }
    await route.fulfill({status: 200, json: data});
  });
  return {email, requests, unexpectedRequests, pageErrors};
}

test('two account tabs stay signed in when profile_image is null', async ({page, context}) => {
  const {email, requests, unexpectedRequests, pageErrors} = await mockStableSession(context, page);
  const firstUnexpectedPaths = watchAccountNavigation(page);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Account Dashboard'})).toBeVisible();
  await expectSignedInAs(page, email);

  const second = await context.newPage();
  second.on('pageerror', (error) => pageErrors.push(error.message));
  await mockHealthyAppShell(second);
  const secondUnexpectedPaths = watchAccountNavigation(second);
  await second.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(second.getByRole('heading', {name: 'Account Dashboard'})).toBeVisible();
  await expectSignedInAs(second, email);

  // Observe a bounded quiet period after both profile requests: a final URL
  // assertion alone can pass momentarily in the middle of the redirect loop.
  await page.waitForTimeout(1_000);

  expect(unexpectedRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(firstUnexpectedPaths).toEqual([]);
  expect(secondUnexpectedPaths).toEqual([]);
  expect(requests.get('GET /authn/session/')).toBeLessThanOrEqual(4);
  // Each tab loads the dashboard profile and the menu's missing-image check.
  expect(requests.get('GET /authn/profile/')).toBe(4);
  for (const tab of [page, second]) {
    await expect(tab).toHaveURL(/\/account$/);
    await expectSignedInAs(tab, email);
    await expect(tab.getByRole('heading', {name: 'Account Dashboard'})).toBeVisible();
  }
});

test('a successful token refresh preserves saved merged projects', async ({page, context}) => {
  const {email, unexpectedRequests, pageErrors} = await mockStableSession(context, page);
  const row = {...pastProjectRows()[0], is_presenting: 'Yes'};
  await page.addInitScript((draft) => {
    sessionStorage.setItem('past-projects:builder:merged-rows', JSON.stringify([draft]));
  }, row);
  await mockPastProjects(page, pastProjectRows());

  const refreshedAccess = mintFakeJwt({exp: Math.floor(Date.now() / 1000) + 172_800});
  let refreshRequests = 0;
  const searchAuthorization: (string | undefined)[] = [];
  await page.route('**/authn/refresh/', async (route) => {
    refreshRequests += 1;
    expect(route.request().postDataJSON()).toEqual({refresh: 'two-tabs-refresh'});
    await route.fulfill({status: 200, json: {access: refreshedAccess, refresh: 'refreshed-token'}});
  });
  await page.route('**/projects/past-ai-search/', async (route) => {
    searchAuthorization.push(route.request().headers().authorization);
    if (searchAuthorization.length === 1) {
      await route.fulfill({status: 401, json: {detail: 'Access token expired.'}});
      return;
    }
    await route.fulfill({status: 200, json: aiSearchResponse({query: 'irrigation'})});
  });

  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  await expectSignedInAs(page, email);
  const savedResults = page.locator('section').filter({
    has: page.getByRole('heading', {name: 'Saved Merged Results', exact: true}),
  });
  await expect(savedResults.getByText(row.project_title, {exact: true}).first()).toBeVisible();
  const originalDraft = await page.evaluate(() => sessionStorage.getItem('past-projects:builder:merged-rows'));

  await page.getByRole('button', {name: '+ AI Search Table'}).click();
  const searchForm = page.locator('.past-projects-ai-search');
  await searchForm.getByPlaceholder('Ask AI to find relevant past projects...').fill('irrigation');
  const sessionRevalidated = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith('/authn/session/') && response.status() === 200,
  );
  await searchForm.getByRole('button', {name: 'Search', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'AI Search Table: irrigation'})).toBeVisible();
  await (await sessionRevalidated).finished();

  expect(refreshRequests).toBe(1);
  expect(searchAuthorization).toHaveLength(2);
  expect(searchAuthorization[1]).toBe(`Bearer ${refreshedAccess}`);
  expect(searchAuthorization[0]).not.toBe(searchAuthorization[1]);
  await expectSignedInAs(page, email);
  await expect(page).toHaveURL(/\/past-projects$/);
  await expect(savedResults.getByText(row.project_title, {exact: true}).first()).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('past-projects:builder:merged-rows'))).toBe(originalDraft);
  expect(unexpectedRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});
