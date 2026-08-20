import type {Page} from '@playwright/test';

/**
 * Structural subset of the CMS-managed `layout-menu` stylesheet (seeded from
 * `src/apps/cms/migrations/data/stylesheets.json`) that `/layout/styles.css`
 * serves in production.
 *
 * An EMPTY sheet is NOT neutral. Those rules are the only thing taking the
 * header's hover dropdowns out of the document flow, and `MemberMenu` mounts
 * `.member-dropdown` conditionally on hover. Without them the dropdown lands in
 * normal flow and mounting/unmounting it reflows the whole page — and because
 * Playwright parks the virtual mouse wherever the last action left it, a stray
 * hover over the header could move the element under test between mousedown and
 * mouseup. The click was reported as delivered but never reached the button
 * (CI run 32107167026: `iphone14` + `ipad` shifted 101px mid-click, so the
 * /subscribe wizard never advanced past the profile step).
 *
 * Structural rules only — everything cosmetic stays out of the mock.
 */
const HEADER_LAYOUT_CSS = `:root {}
.site-header-member,
.menu-bar-item {
  position: relative;
}
.member-dropdown,
.menu-dropdown {
  position: absolute;
  top: 100%;
}
.member-dropdown {
  right: 0;
}
.menu-dropdown {
  left: 0;
}
/* Mirrors the real sheet: below 993px the desktop member menu is not rendered
   at all — the mobile drawer's .header-mobile-member takes over. */
@media (max-width: 992px) {
  .site-header-member {
    display: none;
  }
}`;

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

  await page.route('**/layout/styles.css*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/css',
      body: HEADER_LAYOUT_CSS,
    });
  });

  await page.route('**/analytics/pageview/', async (route) => {
    await route.fulfill({status: 204});
  });

  await page.route('**/assistant/config/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: false,
        welcome_message: '',
        starter_questions: [],
        unavailable_message: 'Assistant disabled in fixture-backed browser tests.',
        max_message_chars: 2000,
      }),
    });
  });

}
