// /past-projects builder mode: multi-search-table workflow with AI search,
// merge/remove/undo/reset. Covers authenticated + unauthenticated
// paths.
import {test, expect} from '../helpers/fixtures';
import {
  aiSearchResponse,
  mockAiSearch,
  mockPastProjects,
  pastProjectRows,
  seedAuthenticatedSession,
} from '../helpers';

test('past projects builder page renders', async ({page}) => {
  await mockPastProjects(page, pastProjectRows());
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Past Projects'})).toBeVisible();
});

test('AI search form submits query and shows results', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, pastProjectRows());
  const {queries} = await mockAiSearch(page, {
    response: aiSearchResponse({results: [pastProjectRows()[0]], query: 'irrigation'}),
  });
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: '+ AI Search Table'}).click();
  const aiSearchForm = page.locator('.past-projects-ai-search');
  await aiSearchForm.getByPlaceholder('Ask AI to find relevant past projects...').fill('irrigation');
  await aiSearchForm.getByRole('button', {name: 'Search'}).click();

  await expect.poll(() => queries.length).toBe(1);
  expect((queries[0] as Record<string, unknown>).query).toBe('irrigation');
  await expect(page.getByRole('heading', {name: 'AI Search Table: irrigation'})).toBeVisible();
  await expect(page.getByText(pastProjectRows()[0].project_title).first()).toBeVisible();
});

test('AI search unavailable state shows message', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, pastProjectRows());
  const {queries} = await mockAiSearch(page, {
    response: aiSearchResponse({available: false, message: 'AI search is unavailable.', query: '', results: []}),
  });
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: '+ AI Search Table'}).click();
  const aiSearchForm = page.locator('.past-projects-ai-search');
  await aiSearchForm.getByPlaceholder('Ask AI to find relevant past projects...').fill('test');
  await aiSearchForm.getByRole('button', {name: 'Search'}).click();

  await expect.poll(() => queries.length).toBe(1);
  await expect(page.getByRole('alert')).toContainText('AI search is unavailable.');
});

test('"Sign in required" dialog shown for unauthenticated AI search', async ({page}) => {
  await page.addInitScript(() => window.sessionStorage.clear());
  await mockPastProjects(page, pastProjectRows());
  const {queries} = await mockAiSearch(page, {status: 401});
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: '+ AI Search Table'}).click();

  await expect(page.getByRole('dialog', {name: 'Sign in required'})).toBeVisible();
  await expect(page.getByText('You need to sign in before using AI search.')).toBeVisible();
  expect(queries).toHaveLength(0);
});
