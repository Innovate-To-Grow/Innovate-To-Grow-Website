// /acknowledgement: an ordinary CMS page served by the CMS catch-all; its copy and sponsors come from the CMS.
import {test, expect} from '../helpers/fixtures';
import {cmsAcknowledgementPage, mockCmsPage} from '../helpers';

test('acknowledgement page renders from the CMS payload', {tag: '@core'}, async ({page}) => {
  await mockCmsPage(page, 'acknowledgement', cmsAcknowledgementPage());
  await page.goto('/acknowledgement', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {level: 1, name: 'Partners & Sponsors'})).toBeVisible();
  await expect(page.getByText('Acme Corp')).toBeVisible();
  await expect(page).toHaveTitle(/Partners & Sponsors/);
});
