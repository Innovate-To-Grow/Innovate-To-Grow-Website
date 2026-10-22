// CMS block layout with the CMS content stylesheets (the shell mock serves an empty sheet):
// an embedded CMS widget sits on the page background, 'left' image + text puts the text in the
// column beside the image, 'right' keeps the float the live capstone pages use, and the hero,
// CTA, notice and numbered-list blocks render with the design system.
import type {Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';
import {cmsEmbedResponse, cmsPageResponse, mockCmsEmbed, mockCmsPage} from '../helpers';
import {serveSeedStylesheets} from '../helpers/stylesheets';

const PARAGRAPH =
  'Teams of UC Merced engineering students partner with organisations to design, build and test systems ' +
  'that solve real problems. Each semester ends with the Innovate to Grow showcase.';
const BODY = `<p>${PARAGRAPH}</p><p>${PARAGRAPH}</p>`;

type Box = {left: number; right: number; top: number; bottom: number; width: number};

async function box(page: Page, selector: string): Promise<Box> {
  return page.locator(selector).first().evaluate((el) => {
    const r = el.getBoundingClientRect();
    return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width};
  });
}

async function openImageTextPage(page: Page, position: 'left' | 'right') {
  await serveSeedStylesheets(page);
  await mockCmsPage(page, 'image-text-layout', cmsPageResponse({
    slug: 'image-text-layout', route: '/image-text-layout', title: 'Image + text',
    blocks: [{block_type: 'image_text', sort_order: 0, data: {
      heading: 'Engineering Capstone',
      image_url: '/assets/about/engineering_capstone.webp',
      image_alt: 'Capstone team',
      image_position: position,
      body_html: BODY,
    }}],
  }));
  await page.goto('/image-text-layout', {waitUntil: 'networkidle'});
  await expect(page.getByRole('img', {name: 'Capstone team'})).toBeVisible();
}

test('an embedded CMS widget sits on the page background; a third-party embed keeps its placeholder', async ({page}) => {
  await page.setViewportSize({width: 1280, height: 900});
  await serveSeedStylesheets(page);
  await page.route('https://www.youtube-nocookie.com/**', (route) =>
    route.fulfill({status: 200, contentType: 'text/html', body: '<!doctype html><title>video</title>'}),
  );
  await mockCmsEmbed(page, 'layout-widget', cmsEmbedResponse({widget_type: 'blocks'}));
  await mockCmsPage(page, 'embed-layout', cmsPageResponse({
    slug: 'embed-layout', route: '/embed-layout', title: 'Embeds',
    blocks: [
      {block_type: 'embed_widget', sort_order: 0, data: {slug: 'layout-widget'}},
      {block_type: 'embed', sort_order: 1, data: {
        src: 'https://www.youtube-nocookie.com/embed/abc123', title: 'Showcase video', aspect_ratio: '16:9',
      }},
    ],
  }));
  await page.goto('/embed-layout', {waitUntil: 'networkidle'});

  const widgetFrame = page.locator('.cms-embed-widget__frame');
  await expect(widgetFrame).toBeVisible();
  await expect(widgetFrame).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(page.locator('.cms-embed__frame')).toHaveCSS('background-color', 'rgb(242, 242, 242)');
});

test("'left' image + text puts the text in the column beside the image", async ({page}) => {
  await page.setViewportSize({width: 1280, height: 900});
  await openImageTextPage(page, 'left');

  const content = await box(page, '.cms-image-text-content');
  const image = await box(page, '.cms-image-text-content > .capstone-hero-image');
  const text = await box(page, '.cms-image-text-body');
  const firstParagraph = await box(page, '.cms-image-text-body p');

  expect(image.left).toBeCloseTo(content.left, 0);
  expect(image.width).toBeCloseTo(content.width / 2, 0);
  // The text starts right of the image and runs to the right edge of the column ...
  expect(text.left).toBeGreaterThan(image.right + 20);
  expect(text.right).toBeCloseTo(content.right, 0);
  expect(text.top).toBeCloseTo(content.top, 0);
  // ... and its first paragraph fills that column instead of a sliver of a 72ch box.
  expect(firstParagraph.left).toBeCloseTo(text.left, 0);
  expect(firstParagraph.right).toBeCloseTo(text.right, 0);
});

test("'right' image + text keeps the floated image the capstone pages use", async ({page}) => {
  await page.setViewportSize({width: 1280, height: 900});
  await openImageTextPage(page, 'right');

  const image = page.locator('.cms-image-text-content > .capstone-hero-image');
  await expect(image).toHaveCSS('float', 'right');
  const content = await box(page, '.cms-image-text-content');
  const imageBox = await box(page, '.cms-image-text-content > .capstone-hero-image');
  const firstParagraph = await box(page, '.cms-image-text-body p');
  expect(imageBox.right).toBeCloseTo(content.right, 0);
  expect(imageBox.width).toBeCloseTo(content.width / 2, 0);
  expect(firstParagraph.left).toBeCloseTo(content.left, 0);
});

test("'left' image + text stacks the image above the text on phones", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await openImageTextPage(page, 'left');

  const content = await box(page, '.cms-image-text-content');
  const image = await box(page, '.cms-image-text-content > .capstone-hero-image');
  const text = await box(page, '.cms-image-text-body');
  expect(image.width).toBeCloseTo(content.width, 0);
  expect(text.top).toBeGreaterThanOrEqual(image.bottom);
  expect(text.width).toBeCloseTo(content.width, 0);
});

test('hero, CTA, notice and numbered-list blocks render with the design system', async ({page}) => {
  await page.setViewportSize({width: 1280, height: 900});
  await serveSeedStylesheets(page);
  await mockCmsPage(page, 'new-blocks', cmsPageResponse({
    slug: 'new-blocks', route: '/new-blocks', title: 'New blocks',
    blocks: [
      {block_type: 'hero', sort_order: 0, data: {heading: 'Hero title', subheading: 'Lead sentence.'}},
      {block_type: 'cta_group', sort_order: 1, data: {items: [
        {label: 'Register', href: '/event-registration', style: 'primary'},
        {label: 'Learn more', href: '/about', style: 'secondary'},
      ]}},
      {block_type: 'notice', sort_order: 2, data: {heading: 'Deadline', style: 'warning', body_html: '<p>Friday.</p>'}},
      {block_type: 'numbered_list', sort_order: 3, data: {heading: 'Steps', items: ['One', 'Two']}},
    ],
  }));
  await page.goto('/new-blocks', {waitUntil: 'networkidle'});

  await expect(page.getByRole('heading', {name: 'Hero title', level: 1})).toHaveCSS('color', 'rgb(15, 45, 82)');
  await expect(page.locator('.cms-hero .itg-lead')).toHaveCSS('border-bottom-color', 'rgb(15, 45, 82)');

  const primary = page.getByRole('link', {name: 'Register'});
  await expect(primary).toHaveCSS('background-color', 'rgb(15, 45, 82)');
  await expect(primary).toHaveCSS('border-radius', '0px');
  const outline = page.getByRole('link', {name: 'Learn more'});
  await expect(outline).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  const [primaryBox, outlineBox] = [await primary.boundingBox(), await outline.boundingBox()];
  expect(outlineBox?.y).toBeCloseTo(primaryBox?.y ?? 0, 0);

  const note = page.getByRole('note');
  await expect(note).toHaveCSS('border-left-color', 'rgb(219, 170, 0)');
  await expect(note).toHaveCSS('background-color', 'rgb(255, 246, 219)');

  await expect(page.locator('.cms-numbered-list ol')).toHaveCSS('list-style-type', 'decimal');
});
