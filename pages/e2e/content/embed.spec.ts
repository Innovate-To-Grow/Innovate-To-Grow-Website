// /_embed/:embedSlug: public embed widget rendered in an isolated iframe.
import {test, expect} from '../helpers/fixtures';
import {cmsEmbedResponse, mockCmsEmbed, mockSchedule, schedulePayload} from '../helpers';

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

// A team listed by its CurrentProject id (not presenting, track 0), so its title links to /projects/<id>.
const linkedSchedule = () => {
  const [project] = schedulePayload().projects;
  return schedulePayload({projects: [{...project, track: 0, order: 0, is_presenting: false}]});
};

test('a project link in an embedded Current Projects widget opens in a new tab, leaving the widget', async ({page}) => {
  await mockSchedule(page, linkedSchedule());
  await mockCmsEmbed(page, 'projects-widget', cmsEmbedResponse({widget_type: 'app_route', app_route: '/current-projects', blocks: []}));
  await page.goto('/_embed/projects-widget', {waitUntil: 'domcontentloaded'});

  const popup = page.context().waitForEvent('page');
  await page.getByRole('link', {name: 'Adaptive Irrigation Dashboard', exact: true}).filter({visible: true}).click();
  const tab = await popup;
  await tab.waitForURL(/\/projects\/project-e2e-1$/);
  await tab.close();

  await expect(page).toHaveURL(/\/_embed\/projects-widget$/);
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
});

test('"Section titles" hides the page header of an embedded project page', async ({page}) => {
  await mockSchedule(page, linkedSchedule());
  await mockCmsEmbed(page, 'projects-no-titles', cmsEmbedResponse({
    widget_type: 'app_route',
    app_route: '/current-projects',
    blocks: [],
    hidden_sections: ['section_titles'],
  }));
  await page.goto('/_embed/projects-no-titles', {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('link', {name: 'Adaptive Irrigation Dashboard', exact: true}).filter({visible: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeHidden();
  // The meta line ("N projects · …") is there once the rows load, and goes with the rest of the header.
  const meta = page.locator('.projects-page .itg-page-meta');
  await expect(meta).toHaveCount(1);
  await expect(meta).toBeHidden();
  await expect(page.locator('.projects-page .itg-lead')).toBeHidden();
});

test('an app-route widget keeps its controls off the frame edge: 16px in, 20px on phones', {tag: '@core'}, async ({page}) => {
  await mockSchedule(page, linkedSchedule());
  await mockCmsEmbed(page, 'projects-widget', cmsEmbedResponse({widget_type: 'app_route', app_route: '/current-projects', blocks: []}));
  await page.goto('/_embed/projects-widget', {waitUntil: 'domcontentloaded'});

  const title = page.getByRole('heading', {level: 1, name: 'Current Projects'});
  await expect(title).toBeVisible();
  const inset = (page.viewportSize()?.width ?? 1280) <= 768 ? 20 : 16;
  const box = await title.boundingBox();
  expect(Math.round(box?.x ?? -1)).toBe(inset);
  await expect(page.locator('.cms-embed-app-route')).toHaveCSS('padding-left', `${inset}px`);
  // The page background stays, so the widget's text and stripes keep their contrast on a coloured host page.
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
});
