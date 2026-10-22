// Page shell around the routed page: the phone header's reserved room, the
// mobile-menu bar, the phone empty-state targets and the main landmark.
// These checks need the CMS content sheets as well as the bundled shell CSS.
import {test, expect} from '../helpers/fixtures';
import {cmsEmbedResponse, mockCmsEmbed} from '../helpers';
import {serveSeedStylesheets} from '../helpers/stylesheets';

const PHONE = {width: 390, height: 844};

test.beforeEach(async ({page}) => {
  await serveSeedStylesheets(page);
});

test('isolated routes reserve no room for the header that they do not mount', async ({page}) => {
  await page.setViewportSize(PHONE);
  await mockCmsEmbed(page, 'shell-embed', cmsEmbedResponse({widget_type: 'blocks'}));

  for (const path of ['/_embed/shell-embed', '/_block-preview', '/login?_isolated=1']) {
    await page.goto(path, {waitUntil: 'domcontentloaded'});
    await expect(page.locator('html')).toHaveAttribute('data-block-preview', '');
    await expect(page.locator('#menu-root')).toBeEmpty();
    expect(await page.locator('#main').evaluate((main) => main.getBoundingClientRect().top), path).toBe(0);
  }

  // A normal page still keeps the fixed phone bar + band's room above the content.
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.site-header-band')).toBeVisible();
  const room = await page.evaluate(() => ({
    mainTop: document.getElementById('main')!.getBoundingClientRect().top,
    bandBottom: document.querySelector('.site-header-band')!.getBoundingClientRect().bottom,
  }));
  expect(room.mainTop).toBeGreaterThan(100);
  expect(Math.abs(room.mainTop - room.bandBottom)).toBeLessThanOrEqual(1);
});

test('the phone site-name band never leaves its room empty while scrolling', async ({page}) => {
  await page.setViewportSize(PHONE);
  // No transitions: each scroll position settles at once.
  await page.emulateMedia({reducedMotion: 'reduce'});
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.addStyleTag({content: '#footer-root { min-height: 3000px; }'});
  await expect(page.locator('.site-header-band')).toBeVisible();

  const scrollTo = (y: number) => page.evaluate((top) => window.scrollTo(0, top), y);
  // Height of any blank strip between the header (bar, or bar + band) and the page content.
  const emptyStrip = () =>
    page.evaluate(() => {
      const bar = document.querySelector('.site-header-bar')!.getBoundingClientRect();
      const bandElement = document.querySelector('.site-header-band')!;
      const band = bandElement.getBoundingClientRect();
      const coveredTo = getComputedStyle(bandElement).visibility === 'hidden' ? bar.bottom : Math.max(bar.bottom, band.bottom);
      const contentTop = document.getElementById('menu-root')!.getBoundingClientRect().bottom;
      return Math.max(0, Math.round(contentTop - coveredTo));
    });
  const header = page.locator('.site-header');

  for (const y of [10, 30, 50, 70]) {
    await scrollTo(y);
    await expect.poll(emptyStrip, {message: `down to ${y}px`}).toBe(0);
  }
  await scrollTo(400);
  await expect(header).toHaveClass(/is-band-hidden/);
  await expect.poll(emptyStrip).toBe(0);

  // Back up, but not to the very top: the band returns as soon as its room is in view.
  for (const y of [200, 90, 60, 20, 10]) {
    await scrollTo(y);
    await expect.poll(emptyStrip, {message: `up to ${y}px`}).toBe(0);
  }
  await expect(header).not.toHaveClass(/is-band-hidden/);
});

test('the open mobile menu repeats the site bar at the same 80px + 5px height', async ({page}) => {
  await page.setViewportSize(PHONE);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});

  const bar = page.locator('.site-header-bar');
  await expect(bar).toBeVisible();
  const closedHeight = await bar.evaluate((element) => element.getBoundingClientRect().height);
  expect(closedHeight).toBe(85);

  await page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'}).click();
  const top = page.locator('#mobile-menu .header-mobile-top');
  await expect(top).toBeVisible();
  const open = await top.evaluate((element) => ({
    height: element.getBoundingClientRect().height,
    border: getComputedStyle(element).borderBottomWidth,
  }));
  expect(open).toEqual({height: closedHeight, border: '5px'});
});

test('empty-state text links are 44px touch targets on phones', async ({page}) => {
  await page.setViewportSize(PHONE);
  await page.route('**/cms/pages/**', (route) =>
    route.fulfill({status: 404, contentType: 'application/json', body: JSON.stringify({detail: 'Not found.'})}),
  );
  await page.goto('/this-page-does-not-exist', {waitUntil: 'domcontentloaded'});

  const link = page.locator('.itg-empty-state-actions').getByRole('link', {name: 'Browse projects'});
  await expect(link).toBeVisible();
  expect((await link.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
});

test('the page content is one native main landmark that the skip link focuses', async ({page}) => {
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('main')).toHaveCount(1);
  await expect(page.locator('main#main')).toHaveCount(1);

  await page.getByRole('link', {name: 'Skip to main content'}).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('main#main')).toBeFocused();
});
