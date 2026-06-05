import {expect, test, type Locator, type Page} from '@playwright/test';

// Live, DB-touching admin dark-mode suite. Mirrors admin.spec.ts: it hits the
// real Django backend (no app-shell mocks, so it imports `test` from
// @playwright/test directly), and the @admin tag pins it to the chromium
// project + the live-backend e2e leg (see playwright.config.ts) — firefox,
// webkit, and the mobile devices skip it.
const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
const adminEmail = process.env.ADMIN_E2E_EMAIL ?? 'admin-e2e@example.com';
const adminPassword = process.env.ADMIN_E2E_PASSWORD ?? 'admin-e2e-password';

// `body`/`#main` get `background: var(--md-sys-color-surface) !important` and
// `#nav-sidebar`/`header`/`.breadcrumbs` get `--md-sys-color-surface-container`
// in google-material-admin.css — both flip between light (#fffbfb / #f6f3f3)
// and dark (#131314 / #202124). They are opaque, token-driven surfaces, which
// makes them reliable luminance probes for "did dark mode actually apply".
const LIGHT_SURFACE = '#main';
const SIDEBAR_SURFACE = '#nav-sidebar';
// Perceived-luminance midpoint (0–255). Dark surfaces land ~19–32, light ~240+.
const LUMINANCE_MIDPOINT = 128;

async function adminLogin(page: Page, email = adminEmail, password = adminPassword) {
  await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.login-title, h1, [role="heading"]').first()).toBeVisible();

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/admin\/?(?:\?.*)?$/);
}

// Computed background colour of `selector` as perceived luminance (0–255).
// Throws on a transparent background so a bad probe target fails loudly
// instead of silently reading as "black".
async function backgroundLuminance(page: Page, selector: string): Promise<number> {
  const probe = page.locator(selector).first();
  await expect(probe, `${selector} should be present for a luminance probe`).toBeAttached();
  return probe.evaluate((el) => {
    const raw = getComputedStyle(el).backgroundColor;
    const match = raw.match(/rgba?\(([^)]+)\)/);
    if (!match) throw new Error(`Unparseable background-color "${raw}" for luminance probe`);
    const parts = match[1].split(',').map((value) => Number.parseFloat(value.trim()));
    const [r, g, b, a = 1] = parts;
    if (a === 0) throw new Error(`Transparent background-color "${raw}" is not a valid luminance probe`);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  });
}

function themeToggleButton(page: Page): Locator {
  return page.getByRole('button', {name: 'Switch admin theme'});
}

// The dropdown panel. Keyed by its stable class rather than the ARIA role:
// the panel animates in/out via Alpine x-transition, and a role-based
// `navigation` locator drops out of the accessibility tree the moment it hits
// `display:none`, which makes visibility assertions race the leave animation.
function themeMenu(page: Page): Locator {
  return page.locator('.i2g-admin-theme-toggle__menu');
}

// Wait until the menu panel has fully finished its x-transition to `display:none`.
// Re-opening the menu while its leave transition is still running races Alpine's
// `x-on:click.outside` handler, which swallows the open click (the button's
// `aria-expanded` never flips to true) — so each open must start from a
// definitively-closed panel, not merely from `aria-expanded === 'false'`.
async function expectThemeMenuClosed(page: Page) {
  await page.waitForFunction(() => {
    const menu = document.querySelector('.i2g-admin-theme-toggle__menu');
    return !menu || getComputedStyle(menu).display === 'none';
  });
}

// Open the theme menu and pick Light / Dark / System by its option label.
async function selectTheme(page: Page, option: 'Light' | 'Dark' | 'System') {
  const button = themeToggleButton(page);
  // Guard against a still-animating leave transition from a previous select.
  await expectThemeMenuClosed(page);

  await button.click();
  // The button binds `aria-expanded` straight to Alpine's `openTheme`, so it
  // flips synchronously with the state — a transition-free signal the menu is
  // open. Also wait for the panel to actually paint before clicking into it.
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await expect(themeMenu(page)).toBeVisible();

  await themeMenu(page).getByRole('button', {name: option, exact: true}).click();
  await expect(button).toHaveAttribute('aria-expanded', 'false');
  // Settle the panel fully closed so a subsequent selectTheme opens cleanly.
  await expectThemeMenuClosed(page);
}

function htmlClassList(page: Page): Promise<string[]> {
  return page.evaluate(() => Array.from(document.documentElement.classList));
}

test.describe.serial('Django admin dark mode', {tag: '@admin'}, () => {
  test('exposes the three-way theme toggle in the authenticated admin header', async ({page}) => {
    await adminLogin(page);

    await expect(page.getByTestId('i2g-admin-theme-toggle')).toBeVisible();
    await themeToggleButton(page).click();
    const menu = page.getByRole('navigation', {name: 'Admin theme options'});
    await expect(menu.getByRole('button', {name: 'Light', exact: true})).toBeVisible();
    await expect(menu.getByRole('button', {name: 'Dark', exact: true})).toBeVisible();
    await expect(menu.getByRole('button', {name: 'System', exact: true})).toBeVisible();
  });

  test('selecting Dark applies the .dark class and renders genuinely dark surfaces', async ({page}) => {
    await adminLogin(page);

    // Start from a known-light baseline so the assertion proves the switch.
    await selectTheme(page, 'Light');
    expect(await htmlClassList(page)).not.toContain('dark');
    expect(await backgroundLuminance(page, LIGHT_SURFACE)).toBeGreaterThan(LUMINANCE_MIDPOINT);

    await selectTheme(page, 'Dark');
    expect(await htmlClassList(page)).toContain('dark');
    expect(await backgroundLuminance(page, LIGHT_SURFACE)).toBeLessThan(LUMINANCE_MIDPOINT);
  });

  test('selecting Light removes the .dark class and restores light surfaces', async ({page}) => {
    await adminLogin(page);

    await selectTheme(page, 'Dark');
    expect(await htmlClassList(page)).toContain('dark');

    await selectTheme(page, 'Light');
    expect(await htmlClassList(page)).not.toContain('dark');
    expect(await backgroundLuminance(page, LIGHT_SURFACE)).toBeGreaterThan(LUMINANCE_MIDPOINT);
  });

  test('persists the chosen dark theme across a full page reload', async ({page}) => {
    await adminLogin(page);

    await selectTheme(page, 'Dark');
    expect(await htmlClassList(page)).toContain('dark');

    await page.reload({waitUntil: 'domcontentloaded'});

    // The persisted `adminTheme` (Alpine $persist → localStorage) must re-apply
    // `.dark` on load without any further interaction.
    await expect(page.locator('html.dark')).toBeAttached();
    expect(await backgroundLuminance(page, LIGHT_SURFACE)).toBeLessThan(LUMINANCE_MIDPOINT);
  });

  test('keeps admin chrome dark on a changelist — no light sidebar or content panels', async ({page}) => {
    await adminLogin(page);
    await selectTheme(page, 'Dark');

    // Navigate to a real changelist; the persisted theme should carry over and
    // the sidebar + main content surfaces must both be dark, not white.
    await page.goto(`${apiBaseUrl}/admin/projects/project/`, {waitUntil: 'domcontentloaded'});
    await expect(page.locator('html.dark')).toBeAttached();
    await expect(page.locator('body')).not.toContainText(/Traceback|Internal Server Error/i);

    expect(await backgroundLuminance(page, LIGHT_SURFACE)).toBeLessThan(LUMINANCE_MIDPOINT);
    expect(await backgroundLuminance(page, SIDEBAR_SURFACE)).toBeLessThan(LUMINANCE_MIDPOINT);

    // Reset to light so a serial rerun / other suites start from a clean theme.
    await selectTheme(page, 'Light');
  });

  test('locks the dark checkbox-checkmark fix this PR ships', async ({page}) => {
    // The surface/sidebar luminance probes above would still pass if the PR's
    // CSS fixes were reverted (those surfaces are painted by pre-existing
    // rules). This test pins the actual change in google-material-admin-overrides.css:
    // in dark mode the checked changelist action-checkbox must draw its SVG
    // checkmark with the dark on-primary stroke (#202124), NOT the light-mode
    // white stroke (%23fff) that would be near-invisible on the light-blue fill.
    await adminLogin(page);
    await selectTheme(page, 'Dark');

    await page.goto(`${apiBaseUrl}/admin/projects/project/`, {waitUntil: 'domcontentloaded'});
    await expect(page.locator('html.dark')).toBeAttached();

    const checkbox = page.locator('#changelist input.action-select').first();
    await expect(checkbox).toBeVisible();
    await checkbox.check();

    const checkmark = await checkbox.evaluate((el) => decodeURIComponent(getComputedStyle(el).backgroundImage));
    expect(checkmark, 'checked action-checkbox should render an inline SVG checkmark').toContain('data:image/svg+xml');
    expect(checkmark, 'dark-mode checkmark must use the #202124 stroke').toContain('#202124');
    expect(checkmark, 'dark-mode checkmark must not keep the light white (#fff) stroke').not.toContain("stroke='#fff'");

    await selectTheme(page, 'Light');
  });
});
