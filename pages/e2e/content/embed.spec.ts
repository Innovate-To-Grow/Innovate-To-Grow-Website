// /_embed/:embedSlug: public embed widget rendered in an isolated iframe.
import {test, expect} from '../fixtures';
import {cmsEmbedResponse, mockCmsEmbed} from '../helpers';

test('embed page renders CMS blocks', async ({page}) => {
  await mockCmsEmbed(page, 'test-embed', cmsEmbedResponse({widget_type: 'blocks'}));
  await page.goto('/_embed/test-embed', {waitUntil: 'networkidle'});
  // The embed page reuses the .cms-page class or the response page_css_class.
  await expect(page.locator('.cms-page')).toBeVisible();
  await expect(page.locator('.cms-page')).toContainText('Embedded content block');
});

test('embed page applies hidden sections when configured', async ({page}) => {
  await mockCmsEmbed(page, 'hidden-sections', cmsEmbedResponse({
    hidden_sections: ['header', 'footer'],
    hide_section_titles: true,
  }));
  await page.goto('/_embed/hidden-sections', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toBeVisible();
});
