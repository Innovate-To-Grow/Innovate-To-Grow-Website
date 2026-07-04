// /events/:eventSlug: past event archive. Event slugs are configured server-side
// so unknown slugs show the "Event Not Found" state.
import {test, expect} from '../fixtures';

test('event archive shows Event Not Found for an unknown slug', async ({page}) => {
  await page.goto('/events/not-a-real-slug', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Event Not Found'})).toBeVisible();
  await expect(page.getByRole('link', {name: 'View all past events'})).toBeVisible();
});
