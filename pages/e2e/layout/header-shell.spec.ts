// Page shell around the routed page: the phone header's reserved room, the
// mobile-menu bar, the phone empty-state targets and the main landmark.
// The bundle carries all of the site's CSS, so the shell mock's empty /layout/theme.css is enough.
import {test, expect} from '../helpers/fixtures';
import {cmsEmbedResponse, mockCmsEmbed} from '../helpers';

const PHONE = {width: 390, height: 844};

test('isolated routes reserve no room for the header that they do not mount', async ({page}) => {
  await page.setViewportSize(PHONE);
  await mockCmsEmbed(page, 'shell-embed', cmsEmbedResponse({widget_type: 'blocks'}));

  for (const path of ['/_embed/shell-embed', '/_block-preview', '/login?_isolated=1']) {
    await page.goto(path, {waitUntil: 'domcontentloaded'});
    await expect(page.locator('html')).toHaveAttribute('data-block-preview', '');
    await expect(page.locator('#menu-root')).toBeEmpty();
    expect(await page.locator('#main').evaluate((main) => main.getBoundingClientRect().top), path).toBe(0);
  }

  // A normal page still keeps the fixed phone bar's room above the content.
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.site-header-bar')).toBeVisible();
  const room = await page.evaluate(() => ({
    mainTop: document.getElementById('main')!.getBoundingClientRect().top,
    barBottom: document.querySelector('.site-header-bar')!.getBoundingClientRect().bottom,
  }));
  expect(room.mainTop).toBeGreaterThan(50);
  expect(Math.abs(room.mainTop - room.barBottom)).toBeLessThanOrEqual(1);
});

test('the phone header is one blue bar with the logo and the menu button, the same at every scroll position', async ({page}) => {
  await page.setViewportSize(PHONE);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.addStyleTag({content: '#footer-root { min-height: 3000px; }'});

  const bar = page.locator('.site-header-bar');
  await expect(bar.getByRole('link', {name: 'Innovate To Grow home'})).toBeVisible();
  await expect(bar.getByRole('button', {name: 'Toggle menu'})).toBeVisible();
  await expect(bar.getByRole('link', {name: 'UC Merced'})).toBeHidden();
  await expect(page.locator('.site-header-band')).toBeHidden();

  const scrollTo = (y: number) => page.evaluate((top) => window.scrollTo(0, top), y);
  const barState = () =>
    page.evaluate(() => {
      const rect = (selector: string) => {
        const box = document.querySelector(selector)!.getBoundingClientRect();
        return [box.x, box.y, box.width, box.height].map((value) => Math.round(value));
      };
      const barBottom = document.querySelector('.site-header-bar')!.getBoundingClientRect().bottom;
      const contentTop = document.getElementById('menu-root')!.getBoundingClientRect().bottom;
      return {
        bar: rect('.site-header-bar'),
        logo: rect('.site-header-logo'),
        toggle: rect('.site-header-mobile-toggle'),
        // Any blank strip between the bar and the page content.
        emptyStrip: Math.max(0, Math.round(contentTop - barBottom)),
      };
    });

  const atTop = await barState();
  // 56px bar + the 5px gold rule; the logo at the front, the menu button at the end.
  expect(atTop.bar).toEqual([0, 0, PHONE.width, 61]);
  expect(atTop.logo[0]).toBeLessThan(atTop.toggle[0]);
  expect(atTop.emptyStrip).toBe(0);

  for (const y of [10, 30, 60, 200, 600, 90, 20, 0]) {
    await scrollTo(y);
    await expect.poll(barState, {message: `at ${y}px`}).toEqual(atTop);
  }
  await expect(page.locator('.site-header')).not.toHaveClass(/is-condensed/);
});

test('the phone menu opens right under the bar, and the menu button, Escape or the backdrop close it', async ({page}) => {
  await page.setViewportSize(PHONE);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});

  const toggle = page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'});
  const panel = page.locator('#mobile-menu');
  await toggle.click();
  await expect(panel).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  // No second copy of the bar: the page's own bar stays on screen above the menu.
  await expect(panel.locator('.header-mobile-top, .header-mobile-close')).toHaveCount(0);
  const placement = await page.evaluate(() => ({
    barBottom: document.querySelector('.site-header-bar')!.getBoundingClientRect().bottom,
    panelTop: document.getElementById('mobile-menu')!.getBoundingClientRect().top,
  }));
  expect(Math.abs(placement.panelTop - placement.barBottom)).toBeLessThanOrEqual(0.5);
  await expect(panel.getByRole('button', {name: /sign in \/ sign up/i})).toBeFocused();
  // The covered page is out of reach for screen readers too, while the bar and the menu stay.
  for (const id of ['main', 'footer-root', 'chatbot-root']) await expect(page.locator(`#${id}`)).toHaveAttribute('inert', '');
  await expect(page.getByRole('region', {name: 'Mobile menu'})).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await expect(toggle).toBeFocused();
  for (const id of ['main', 'footer-root', 'chatbot-root']) await expect(page.locator(`#${id}`)).not.toHaveAttribute('inert');

  await toggle.click();
  await expect(panel).toBeVisible();
  await toggle.click();
  await expect(panel).toBeHidden();

  // The dimmed page under the menu's sections closes it too.
  await toggle.click();
  await expect(panel).toBeVisible();
  await page.mouse.click(PHONE.width / 2, PHONE.height - 20);
  await expect(panel).toBeHidden();
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
