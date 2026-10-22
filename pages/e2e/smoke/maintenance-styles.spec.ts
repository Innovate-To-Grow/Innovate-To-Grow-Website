// The maintenance page and the degraded-service banner show when the backend is down, and that
// backend also serves /api/layout/styles.css. Both must stay styled from what ships in the bundle:
// src/app/MaintenanceMode/MaintenanceMode.css plus the fallback tokens in src/assets/tokens.css.
import type {Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';
import {cmsPageResponse, mockCmsPage} from '../helpers';

/** Answers /health/ (registered after the fixture's handler, so this one wins). */
async function mockHealth(page: Page, status: number, body: Record<string, unknown>) {
  await page.route('**/health/', (route) =>
    route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)}),
  );
}

/** Makes the server stylesheet unavailable; returns the URLs of the requests it failed. */
async function failServerStylesheet(page: Page): Promise<string[]> {
  const failed: string[] = [];
  await page.route('**/layout/styles.css*', async (route) => {
    failed.push(route.request().url());
    await route.abort();
  });
  return failed;
}

test.describe('maintenance styles without the server stylesheet', () => {
  test.beforeEach(async ({page}, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium', 'Bundled-style checks run once in desktop Chromium.');
    // The app renders optimistically while /health/ is pending, so the homepage is fetched either way.
    await mockCmsPage(page, '', cmsPageResponse({
      route: '/',
      slug: '',
      title: 'Innovate to Grow',
      blocks: [{block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>Welcome to Innovate to Grow</h2>'}}],
    }));
  });

  test('the maintenance page is styled by the bundled CSS', async ({page}) => {
    await mockHealth(page, 503, {
      status: 'maintenance',
      database: 'ok',
      maintenance: true,
      maintenance_message: 'Back soon',
    });
    const failedSheets = await failServerStylesheet(page);

    await page.goto('/');

    const container = page.locator('.maintenance-container');
    await expect(container).toBeVisible();
    await expect(container).toHaveCSS('position', 'fixed');
    // --itg-color-primary from the fallback tokens (#0f2d52).
    await expect(page.locator('.maintenance-bar')).toHaveCSS('background-color', 'rgb(15, 45, 82)');
    await expect(page.locator('.maintenance-title')).toHaveText('Service Unavailable');
    await expect(page.locator('.maintenance-lead')).toHaveText('Back soon');
    expect(failedSheets.length).toBeGreaterThan(0);
  });

  test('keyboard focus inside the maintenance page shows the bundled focus ring', async ({page}) => {
    await mockHealth(page, 503, {
      status: 'maintenance',
      database: 'ok',
      maintenance: true,
      maintenance_message: 'Back soon',
    });
    const failedSheets = await failServerStylesheet(page);

    await page.goto('/');

    const container = page.locator('.maintenance-container');
    await expect(container).toBeVisible();
    // Clicking the (non-focusable) title moves the sequential focus starting point there, so Tab
    // lands on the first focusable element after it: the footer's "UC Merced" link.
    await page.locator('.maintenance-title').click();
    await page.keyboard.press('Tab');

    const footerLinks = container.locator('.maintenance-footer-links');
    const link = footerLinks.getByRole('link', {name: 'UC Merced'});
    await expect(link).toBeFocused();
    // :focus-visible rule of the fallback layer, --itg-color-secondary from the fallback tokens (#005487).
    await expect(link).toHaveCSS('outline-style', 'solid');
    await expect(link).toHaveCSS('outline-width', '2px');
    await expect(link).toHaveCSS('outline-color', 'rgb(0, 84, 135)');
    await expect(link).toHaveCSS('outline-offset', '2px');

    // Past "School of Engineering" to the staff bypass toggle, a button.
    await page.keyboard.press('Tab');
    await expect(footerLinks.getByRole('link', {name: 'School of Engineering'})).toBeFocused();
    await page.keyboard.press('Tab');
    const toggle = footerLinks.getByRole('button', {name: 'Bypass with Password'});
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveCSS('outline-style', 'solid');
    await expect(toggle).toHaveCSS('outline-width', '2px');
    await expect(toggle).toHaveCSS('outline-color', 'rgb(0, 84, 135)');

    // Back up past both footer links to the logo link in the navy bar, whose ring is white.
    for (let i = 0; i < 3; i += 1) {
      await page.keyboard.press('Shift+Tab');
    }
    const logoLink = container.locator('.maintenance-bar a');
    await expect(logoLink).toBeFocused();
    await expect(logoLink).toHaveCSS('outline-style', 'solid');
    await expect(logoLink).toHaveCSS('outline-width', '2px');
    await expect(logoLink).toHaveCSS('outline-color', 'rgb(255, 255, 255)');
    expect(failedSheets.length).toBeGreaterThan(0);
  });

  test('the degraded-service banner is styled by the bundled CSS', async ({page}) => {
    // Not in maintenance and status not 'ok' -> 'degraded' (src/lib/api/health.ts).
    await mockHealth(page, 200, {status: 'error', database: 'error', maintenance: false, maintenance_message: ''});
    const failedSheets = await failServerStylesheet(page);

    await page.goto('/');

    const banner = page.locator('.service-degraded-banner');
    await expect(banner).toBeVisible();
    // --itg-color-highlight from the fallback tokens (#fff6db), not the transparent default.
    await expect(banner).toHaveCSS('background-color', 'rgb(255, 246, 219)');
    // The banner sits above the page, which keeps rendering.
    await expect(page.getByRole('heading', {name: 'Welcome to Innovate to Grow'})).toBeVisible();
    expect(failedSheets.length).toBeGreaterThan(0);
  });
});
