// /acknowledgement: CMS-backed partners & sponsors page.
import {test, expect} from '../fixtures';
import {cmsAcknowledgementPage, mockCmsPage} from '../helpers';

test('acknowledgement page renders from the CMS payload', {tag: '@core'}, async ({page}) => {
  await mockCmsPage(page, 'acknowledgement', cmsAcknowledgementPage());
  await page.goto('/acknowledgement', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Partners & Sponsors'})).toBeVisible();
  await expect(page.getByText('Loading sponsors...')).toHaveCount(0);
});
