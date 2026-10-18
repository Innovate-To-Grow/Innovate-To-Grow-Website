// CMS block type rendering: exercises each block type through CMSPageComponent.
// Uses the actual block data shapes matching each component's interface.
import {test, expect} from '../helpers/fixtures';
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

test('HeroBlock renders the page title, lead and image in the main column', async ({page}) => {
  await mockCmsPage(page, 'hero', cmsPageResponse({
    slug: 'hero', route: '/hero', title: 'Hero',
    blocks: [{block_type: 'hero', sort_order: 0, data: {
      heading: 'Innovate to Grow', subheading: 'Students and partners solving real problems.',
      image_url: '/assets/images/home_img.jpg', image_alt: 'Showcase floor',
    }}],
  }));
  await page.goto('/hero', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'Innovate to Grow', level: 1})).toBeVisible();
  await expect(page.locator('.cms-hero .itg-lead')).toHaveText('Students and partners solving real problems.');
  await expect(page.getByRole('img', {name: 'Showcase floor'})).toBeVisible();
});

test('CtaGroupBlock renders button links that navigate in the app', async ({page}) => {
  await mockCmsPage(page, 'cta', cmsPageResponse({
    slug: 'cta', route: '/cta', title: 'CTA',
    blocks: [{block_type: 'cta_group', sort_order: 0, data: {items: [
      {label: 'Read the FAQ', href: '/faq', style: 'primary'},
      {label: 'UC Merced', href: 'https://www.ucmerced.edu', style: 'secondary'},
    ]}}],
  }));
  await mockCmsPage(page, 'faq', cmsPageResponse({
    slug: 'faq', route: '/faq', title: 'FAQ',
    blocks: [{block_type: 'rich_text', sort_order: 0, data: {body_html: '<h2>FAQ landing</h2>'}}],
  }));
  await page.goto('/cta', {waitUntil: 'networkidle'});
  const external = page.locator('.cms-cta-group').getByRole('link', {name: /UC Merced/});
  await expect(external).toHaveAttribute('target', '_blank');
  await expect(external).toHaveClass(/itg-btn-outline/);
  await page.getByRole('link', {name: 'Read the FAQ'}).click();
  await expect(page).toHaveURL(/\/faq$/);
  await expect(page.getByRole('heading', {name: 'FAQ landing'})).toBeVisible();
});

test('NoticeBlock renders a callout with its heading and body', async ({page}) => {
  await mockCmsPage(page, 'notice', cmsPageResponse({
    slug: 'notice', route: '/notice', title: 'Notice',
    blocks: [{block_type: 'notice', sort_order: 0, data: {
      heading: 'Registration closes Friday', style: 'warning', body_html: '<p>Sign up before the deadline.</p>',
    }}],
  }));
  await page.goto('/notice', {waitUntil: 'networkidle'});
  const note = page.getByRole('note');
  await expect(note).toHaveClass(/itg-notice-warning/);
  await expect(note.getByRole('heading', {name: 'Registration closes Friday'})).toBeVisible();
  await expect(note).toContainText('Sign up before the deadline.');
});

test('NumberedListBlock renders the preamble and the steps in order', async ({page}) => {
  await mockCmsPage(page, 'steps', cmsPageResponse({
    slug: 'steps', route: '/steps', title: 'Steps',
    blocks: [{block_type: 'numbered_list', sort_order: 0, data: {
      heading: 'How to submit', preamble_html: '<p>Follow these steps:</p>', items: ['Read', 'Write', 'Submit'],
    }}],
  }));
  await page.goto('/steps', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'How to submit'})).toBeVisible();
  await expect(page.locator('.cms-numbered-list-preamble')).toHaveText('Follow these steps:');
  await expect(page.locator('.cms-numbered-list ol > li')).toHaveText(['Read', 'Write', 'Submit']);
});
