// Event archive (hardcoded configs; the not-found path needs no network) and
// the CMS-backed acknowledgement page.
import {test, expect} from './fixtures';
import {cmsAcknowledgementPage, mockCmsPage} from './helpers';

test('event archive shows Event Not Found for an unknown slug', async ({page}) => {
  await page.goto('/events/not-a-real-slug', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Event Not Found'})).toBeVisible();
  await expect(page.getByRole('link', {name: 'View all past events'})).toBeVisible();
});

test('acknowledgement page renders from the CMS payload', {tag: '@core'}, async ({page}) => {
  await mockCmsPage(page, 'acknowledgement', cmsAcknowledgementPage());
  await page.goto('/acknowledgement', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Partners & Sponsors'})).toBeVisible();
  await expect(page.getByText('Loading sponsors...')).toHaveCount(0);
});
