// / (homepage) and catch-all `*`: CMS-powered pages via HomepageResolver and
// CMSPageComponent. Asserts on heading elements rendered from block content
// rather than the (document.title-only) page title.
import {test, expect} from '../helpers/fixtures';
import {cmsPageResponse, mockCmsPage} from '../helpers';

test('homepage renders CMS blocks via HomepageResolver', {tag: '@core'}, async ({page}) => {
  await mockCmsPage(page, '', cmsPageResponse({
    route: '/',
    slug: '',
    title: 'Innovate to Grow',
    blocks: [{block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>Welcome to ITG</h2>'}}],
  }));
  await page.goto('/', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toBeVisible();
  await expect(page.locator('h2')).toContainText('Welcome to ITG');
});

test('homepage YouTube embeds load without changing responsive wrapper geometry', {tag: '@core'}, async ({page}) => {
  await page.route('**/cms/embed-hosts/', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({hosts: ['www.youtube.com'], revision: 'e2e'}),
  }));
  await page.route('https://www.youtube.com/**', (route) => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: '<!doctype html><title>Mock YouTube player</title>',
  }));
  await mockCmsPage(page, '', cmsPageResponse({
    route: '/',
    slug: '',
    title: 'Innovate to Grow',
    page_css: [
      '.video-column { width: min(100%, 320px); }',
      '.video-shell { position: relative; width: 100%; padding-top: 56.25%; }',
      '.video-shell iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }',
    ].join('\n'),
    blocks: [{
      block_type: 'rich_text',
      sort_order: 0,
      data: {
        body_html: '<div class="video-column"><div class="video-shell"><iframe src="https://www.youtube.com/embed/demo" title="Demo"></iframe></div></div>',
      },
    }],
  }));

  await page.goto('/', {waitUntil: 'networkidle'});

  const wrapper = page.locator('.video-shell');
  const iframe = wrapper.locator('iframe');
  await expect(iframe).toBeVisible();
  await expect(iframe).toHaveAttribute('loading', 'lazy');
  const wrapperBox = await wrapper.boundingBox();
  const iframeBox = await iframe.boundingBox();
  expect(wrapperBox).not.toBeNull();
  expect(iframeBox).not.toBeNull();
  expect(iframeBox!.width).toBeCloseTo(wrapperBox!.width, 1);
  expect(iframeBox!.height).toBeCloseTo(wrapperBox!.height, 1);
});

test('catch-all CMS page renders for unknown route', async ({page}) => {
  await mockCmsPage(page, 'about', cmsPageResponse({
    route: '/about', slug: 'about', title: 'About Us',
    blocks: [{block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>About Us</h2>'}}],
  }));
  await page.goto('/about', {waitUntil: 'networkidle'});
  await expect(page.locator('h2')).toContainText('About Us');
});

test('CMS page renders rich text block content', async ({page}) => {
  await mockCmsPage(page, 'mission', cmsPageResponse({
    blocks: [
      {block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>Our Mission</h2><p>Connecting students with industry.</p>'}},
    ],
  }));
  await page.goto('/mission', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'Our Mission'})).toBeVisible();
});

test('CMS page with multiple block types', async ({page}) => {
  await mockCmsPage(page, 'home', cmsPageResponse({
    blocks: [
      {block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>Welcome</h2>'}},
      {block_type: 'sponsor_year', sort_order: 1, data: {year: '2025', sponsors: [{name: 'Acme Corp', logo_url: ''}]}},
    ],
  }));
  await page.goto('/home', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'Welcome'})).toBeVisible();
  await expect(page.locator('.cms-page')).toContainText('Acme Corp');
});

test('CMS page with empty blocks array still mounts', async ({page}) => {
  // Use the homepage route with empty blocks — the page should still mount.
  await mockCmsPage(page, '', cmsPageResponse({blocks: []}));
  await page.goto('/', {waitUntil: 'networkidle'});
  // With zero blocks the container renders empty (zero height), so assert it
  // mounted in the DOM rather than that it is visible.
  await expect(page.locator('.cms-page')).toBeAttached();
});
