import AxeBuilder from '@axe-core/playwright';
import {test, expect} from './fixtures';
import {cmsPageResponse, mockCmsPage, mockSchedule, schedulePayload} from './helpers';

test.describe('required smoke', {tag: '@required-smoke'}, () => {
  test.beforeEach(({page}, testInfo) => {
    void page;
    test.skip(testInfo.project.name !== 'chromium', 'Required smoke runs once in desktop Chromium.');
  });

  test('homepage renders mocked CMS content without accessibility violations', async ({page}) => {
    await mockCmsPage(page, '', cmsPageResponse({
      route: '/',
      slug: '',
      title: 'Innovate to Grow',
      blocks: [{
        block_type: 'rich_text',
        sort_order: 0,
        data: {body_html: '<h2>Welcome to Innovate to Grow</h2><p>Connecting students and industry.</p>'},
      }],
    }));

    await page.goto('/', {waitUntil: 'networkidle'});
    await expect(page.getByRole('heading', {name: 'Welcome to Innovate to Grow'})).toBeVisible();

    const results = await new AxeBuilder({page}).include('.cms-page').analyze();
    expect(results.violations).toEqual([]);
  });

  test('login form is keyboard-ready and has no accessibility violations', async ({page}) => {
    await page.goto('/login', {waitUntil: 'domcontentloaded'});

    const email = page.getByLabel('Email');
    await email.focus();
    await expect(email).toBeFocused();
    await expect(page.getByRole('button', {name: 'Continue', exact: true})).toBeVisible();

    const results = await new AxeBuilder({page}).include('.auth-page').analyze();
    expect(results.violations).toEqual([]);
  });

  test('current projects renders deterministic mocked schedule data', async ({page}) => {
    await mockSchedule(page, schedulePayload());

    await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
    await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
    await expect(page.locator('.projects-page')).toContainText('Adaptive Irrigation Dashboard');
  });

  test('mobile menu traps keyboard focus and returns it on Escape', async ({page}) => {
    await page.setViewportSize({width: 390, height: 844});
    await page.goto('/login', {waitUntil: 'domcontentloaded'});

    const trigger = page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'});
    await trigger.focus();
    await page.keyboard.press('Enter');

    const menu = page.getByRole('dialog', {name: 'Mobile menu'});
    await expect(menu).toBeVisible();
    const focusable = menu.locator(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    const first = focusable.first();
    const last = focusable.last();
    await expect(first).toBeFocused();

    await page.keyboard.press('Shift+Tab');
    await expect(last).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(first).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});
