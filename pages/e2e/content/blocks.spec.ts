// CMS block type rendering: exercises each block type through CMSPageComponent.
// Uses the actual block data shapes matching each component's interface.
import {test, expect} from '../fixtures';
import {cmsPageResponse, mockCmsPage} from '../helpers';

test('RichTextBlock renders HTML content', async ({page}) => {
  await mockCmsPage(page, 'richtext', cmsPageResponse({
    slug: 'richtext', route: '/richtext', title: 'Rich Text',
    blocks: [{block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>Hello</h2><p>World</p>'}}],
  }));
  await page.goto('/richtext', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'Hello'})).toBeVisible();
});

test('ContactInfoBlock renders contact items', async ({page}) => {
  await mockCmsPage(page, 'contact', cmsPageResponse({
    slug: 'contact', route: '/contact', title: 'Contact',
    blocks: [{block_type: 'contact_info', sort_order: 0, data: {
      heading: 'Get in Touch',
      items: [
        {label: 'Email', value: 'hello@example.com', type: 'email'},
        {label: 'Phone', value: '(209) 555-0123', type: 'phone'},
      ],
    }}],
  }));
  await page.goto('/contact', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'Get in Touch'})).toBeVisible();
});

test('FaqListBlock renders questions', async ({page}) => {
  await mockCmsPage(page, 'faq', cmsPageResponse({
    slug: 'faq', route: '/faq', title: 'FAQ',
    blocks: [{block_type: 'faq_list', sort_order: 0, data: {
      heading: 'FAQ',
      items: [{question: 'What is ITG?', answer_html: '<p>A program at UC Merced.</p>'}],
    }}],
  }));
  await page.goto('/faq', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toContainText('What is ITG?');
});

test('ImageTextBlock renders with body_html', async ({page}) => {
  await mockCmsPage(page, 'imagetext', cmsPageResponse({
    slug: 'imagetext', route: '/imagetext', title: 'Image + Text',
    blocks: [{block_type: 'image_text', sort_order: 0, data: {
      heading: 'Our Story', image_url: '', image_alt: '', body_html: '<p>Since 2015.</p>',
    }}],
  }));
  await page.goto('/imagetext', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'Our Story'})).toBeVisible();
});

test('LinkListBlock renders link items', async ({page}) => {
  await mockCmsPage(page, 'links', cmsPageResponse({
    slug: 'links', route: '/links', title: 'Links',
    blocks: [{block_type: 'link_list', sort_order: 0, data: {
      heading: 'Useful Links',
      items: [{label: 'UC Merced', url: 'https://ucmerced.edu'}],
    }}],
  }));
  await page.goto('/links', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toContainText('UC Merced');
});

test('NavigationGridBlock renders nav items', async ({page}) => {
  await mockCmsPage(page, 'navgrid', cmsPageResponse({
    slug: 'navgrid', route: '/navgrid', title: 'Navigation',
    blocks: [{block_type: 'navigation_grid', sort_order: 0, data: {
      heading: 'Explore',
      items: [{title: 'Projects', url: '/current-projects'}],
    }}],
  }));
  await page.goto('/navgrid', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toContainText('Projects');
});

test('SponsorYearBlock renders sponsor names', async ({page}) => {
  await mockCmsPage(page, 'sponsors', cmsPageResponse({
    slug: 'sponsors', route: '/sponsors', title: 'Sponsors',
    blocks: [{block_type: 'sponsor_year', sort_order: 0, data: {
      year: '2026', sponsors: [{name: 'Acme Corp', logo_url: ''}],
    }}],
  }));
  await page.goto('/sponsors', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toContainText('Acme Corp');
});

test('TableBlock renders tabular data', async ({page}) => {
  await mockCmsPage(page, 'table', cmsPageResponse({
    slug: 'table', route: '/table', title: 'Data Table',
    blocks: [{block_type: 'table', sort_order: 0, data: {
      heading: 'Results',
      columns: ['Name', 'Score'],
      rows: [['Team A', '95']],
    }}],
  }));
  await page.goto('/table', {waitUntil: 'networkidle'});
  await expect(page.locator('.cms-page')).toContainText('Team A');
});
