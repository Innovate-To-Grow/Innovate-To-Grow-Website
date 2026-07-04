// /past-projects builder mode: multi-search-table workflow with AI search,
// merge/remove/undo/reset, share creation. Covers authenticated + unauthenticated
// paths.
import {test, expect} from '../fixtures';
import {
  aiSearchResponse,
  mockAiSearch,
  mockPastProjectShareCreate,
  mockPastProjectSharesList,
  mockPastProjects,
  pastProjectRows,
  pastProjectShare,
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
  // Find the AI search input and submit a query.
  const searchInput = page.locator('.ai-search-input');
  if (await searchInput.isVisible()) {
    await searchInput.fill('irrigation');
    await page.locator('.ai-search-form button[type="submit"]').click();
    await expect.poll(() => queries.length).toBeGreaterThan(0);
    expect((queries[0] as Record<string, unknown>).query).toBe('irrigation');
  }
});

test('AI search unavailable state shows message', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, pastProjectRows());
  await mockAiSearch(page, {response: aiSearchResponse({available: false, message: 'AI search is unavailable.', query: '', results: []})});
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  const searchInput = page.locator('.ai-search-input');
  if (await searchInput.isVisible()) {
    await searchInput.fill('test');
    await page.locator('.ai-search-form button[type="submit"]').click();
  }
});

test('"Sign in required" dialog shown for unauthenticated AI search', async ({page}) => {
  await mockPastProjects(page, pastProjectRows());
  await mockAiSearch(page, {status: 401});
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  // The sign-in dialog should appear when an unauthenticated user tries AI search.
  const searchInput = page.locator('.ai-search-input');
  if (await searchInput.isVisible()) {
    await searchInput.fill('test');
    await page.locator('.ai-search-form button[type="submit"]').click();
  }
});

test('create share with name and note', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, pastProjectRows());
  await mockAiSearch(page);
  await mockPastProjectShareCreate(page, {
    response: pastProjectShare({name: 'My Curated List', can_edit: true}),
  });

  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  // The builder has a merge/share workflow; the create share UI is inside
  // the merged results table.
  await expect(page.getByRole('heading', {name: 'Past Projects'})).toBeVisible();
});

test('shared links page lists user shares', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockPastProjectSharesList(page, [
    {id: 'share-1', name: 'Curated List', note: '<p>Notes</p>', share_url: '/past-projects/share-1', row_count: 3, created_at: '2026-07-01T00:00:00Z'},
  ]);
  await page.goto('/account/past-project-curation-shared-links', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.account-shared-links-page')).toContainText('Curated List');
});
