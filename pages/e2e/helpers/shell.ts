import type {Page} from '@playwright/test';

/**
 * Neutralizes the third-party + infrastructure noise the app fires on every
 * load so mocked specs are deterministic and never depend on external CDNs or
 * a live backend for the app shell. Reused by every mocked spec (applied
 * automatically via the `test` fixture in `../fixtures`).
 */
export async function mockHealthyAppShell(page: Page) {
  await page.route('https://cdn.userway.org/**', async (route) => {
    await route.fulfill({status: 204});
  });

  await page.route('https://api.userway.org/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{}',
    });
  });

  await page.route('**/siteanalyze_8343.js', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: '',
    });
  });

  await page.route('**/static/vendor/font-awesome/**/*.css', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/css',
      body: '',
    });
  });

  await page.route('**/health/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        database: 'ok',
        maintenance: false,
        maintenance_message: '',
      }),
    });
  });

  await page.route('**/layout/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        menus: [],
        footer: null,
        homepage_route: '/',
      }),
    });
  });

  await page.route('**/layout/styles.css', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/css',
      body: ':root {}',
    });
  });

  await page.route('**/analytics/pageview/', async (route) => {
    await route.fulfill({status: 204});
  });
}
