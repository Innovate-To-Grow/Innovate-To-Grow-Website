// CMS "Embed CMS Widget" blocks pointed at the /schedule app route can each pin
// a different CurrentProjectSchedule (e.g. 2025 vs 2026) while reusing the same
// CMSEmbedWidget. Inside the iframe the schedule resolves as:
//   block data.schedule_id (carried as ?schedule_id= on the iframe URL)
//   > widget default (schedule_id on the /cms/embed/<slug>/ payload)
//   > active schedule (no schedule_id sent to /event/schedule/).
// The standalone /schedule route reads ?schedule_id= from its own URL.
import type {Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';
import {cmsEmbedResponse, cmsPageResponse, mockCmsEmbed, mockCmsPage, schedulePayload} from '../helpers';
import type {CMSBlock} from '../../src/features/cms/api';
import type {EmbedWidgetData} from '../../src/features/cms/components/blocks/content/EmbedWidgetBlock';

const UUID_A = '11111111-1111-4111-8111-111111111111';
const UUID_B = '22222222-2222-4222-8222-222222222222';
const WIDGET_SLUG = 'schedule-widget';

const EVENT_NAMES: Record<string, string> = {
  [UUID_A]: 'Innovate to Grow 2025',
  [UUID_B]: 'Innovate to Grow 2026',
};
const ACTIVE_EVENT_NAME = 'Innovate to Grow Active';

const EMBED_IFRAMES = 'iframe[src^="/_embed/"]';
const HEADER_TITLE = '[data-embed-section="schedule-header"] .schedule-page-title';

/**
 * Stubs /event/schedule/ so the response depends on the `schedule_id` query:
 * a known id returns that year's event, no id returns the active event, and an
 * unknown id 404s exactly like `CurrentEventScheduleView` does. Playwright
 * routes apply to iframe requests too, so the embed iframes hit this handler.
 * Returns the `schedule_id` values requested so far (null = no query param).
 */
async function mockScheduleById(page: Page): Promise<Array<string | null>> {
  const requested: Array<string | null> = [];
  await page.route(/\/event\/schedule\/(?:\?.*)?$/, (route) => {
    const scheduleId = new URL(route.request().url()).searchParams.get('schedule_id');
    requested.push(scheduleId);
    if (scheduleId && !EVENT_NAMES[scheduleId]) {
      return route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({detail: 'No schedule configured.'}),
      });
    }
    const base = schedulePayload();
    const payload = schedulePayload({
      event: {
        ...base.event,
        id: scheduleId ?? 'active-schedule',
        name: scheduleId ? EVENT_NAMES[scheduleId] : ACTIVE_EVENT_NAME,
      },
    });
    return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(payload)});
  });
  return requested;
}

function embedWidgetBlock(sortOrder: number, data: Partial<EmbedWidgetData> = {}): CMSBlock {
  return {block_type: 'embed_widget', sort_order: sortOrder, data: {slug: WIDGET_SLUG, ...data}};
}

/**
 * Embed iframes are `loading="lazy"`. Once the first ones auto-resize to their
 * content, later ones end up far below the fold; Firefox/WebKit (unlike
 * Chromium) do not fetch them until they approach the viewport — which is what
 * a real visitor's scroll does — so scroll each one into view before reading it.
 */
async function expectEmbedTitle(page: Page, index: number, title: string): Promise<void> {
  await page.locator(EMBED_IFRAMES).nth(index).scrollIntoViewIfNeeded();
  // Each iframe boots the whole SPA, so allow more than the default expect timeout.
  await expect(page.frameLocator(EMBED_IFRAMES).nth(index).locator(HEADER_TITLE)).toHaveText(title, {
    timeout: 20_000,
  });
}

test('three embed blocks sharing one widget each render their own schedule year', {tag: '@core'}, async ({page}) => {
  const requested = await mockScheduleById(page);
  // Widget has no default schedule, so only the block override or the active schedule applies.
  await mockCmsEmbed(page, WIDGET_SLUG, cmsEmbedResponse({
    widget_type: 'app_route',
    app_route: '/schedule',
    blocks: [],
    schedule_id: null,
  }));
  await mockCmsPage(page, 'schedules', cmsPageResponse({
    route: '/schedules',
    slug: 'schedules',
    title: 'Schedules',
    blocks: [
      embedWidgetBlock(0, {heading: '2025 Schedule', schedule_id: UUID_A}),
      embedWidgetBlock(1, {heading: '2026 Schedule', schedule_id: UUID_B, hidden_sections: ['schedule_projects']}),
      embedWidgetBlock(2, {heading: 'Active Schedule'}),
    ],
  }));

  await page.goto('/schedules', {waitUntil: 'domcontentloaded'});

  const iframes = page.locator(EMBED_IFRAMES);
  await expect(iframes).toHaveCount(3);
  await expect(iframes.nth(0)).toHaveAttribute('src', `/_embed/${WIDGET_SLUG}?schedule_id=${UUID_A}`);
  await expect(iframes.nth(1)).toHaveAttribute(
    'src',
    `/_embed/${WIDGET_SLUG}?hide-sections=schedule_projects&schedule_id=${UUID_B}`,
  );
  await expect(iframes.nth(2)).toHaveAttribute('src', `/_embed/${WIDGET_SLUG}`);

  await expectEmbedTitle(page, 0, 'Innovate to Grow 2025');
  await expectEmbedTitle(page, 1, 'Innovate to Grow 2026');
  await expectEmbedTitle(page, 2, 'Innovate to Grow Active');

  // The hide-sections query still travels alongside schedule_id.
  const frames = page.frameLocator(EMBED_IFRAMES);
  await expect(frames.nth(1).locator('[data-embed-section="schedule-projects"]')).toBeHidden();
  await expect(frames.nth(0).locator('[data-embed-section="schedule-projects"]')).toBeAttached();
  await expect(frames.nth(0).locator('[data-embed-section="schedule-projects"]')).not.toHaveCSS('display', 'none');

  // Each iframe asked the API for exactly its own schedule (none for the active one).
  expect(new Set(requested)).toEqual(new Set([UUID_A, UUID_B, null]));
});

test('block schedule beats widget default, which beats the active schedule', {tag: '@core'}, async ({page}) => {
  const requested = await mockScheduleById(page);
  // This widget pins 2026 by default; a sibling widget has no default at all.
  await mockCmsEmbed(page, WIDGET_SLUG, cmsEmbedResponse({
    widget_type: 'app_route',
    app_route: '/schedule',
    blocks: [],
    schedule_id: UUID_B,
  }));
  await mockCmsEmbed(page, 'plain-schedule', cmsEmbedResponse({
    widget_type: 'app_route',
    app_route: '/schedule',
    blocks: [],
    schedule_id: null,
  }));
  await mockCmsPage(page, 'precedence', cmsPageResponse({
    route: '/precedence',
    slug: 'precedence',
    title: 'Schedule precedence',
    blocks: [
      embedWidgetBlock(0, {heading: 'Block override', schedule_id: UUID_A}),
      embedWidgetBlock(1, {heading: 'Malformed block override', schedule_id: 'not-a-uuid'}),
      embedWidgetBlock(2, {heading: 'Widget default'}),
      embedWidgetBlock(3, {slug: 'plain-schedule', heading: 'No override, no default'}),
    ],
  }));

  await page.goto('/precedence', {waitUntil: 'domcontentloaded'});

  const iframes = page.locator(EMBED_IFRAMES);
  await expect(iframes).toHaveCount(4);
  await expect(iframes.nth(0)).toHaveAttribute('src', `/_embed/${WIDGET_SLUG}?schedule_id=${UUID_A}`);
  // A malformed block id never reaches the iframe URL.
  await expect(iframes.nth(1)).toHaveAttribute('src', `/_embed/${WIDGET_SLUG}`);
  await expect(iframes.nth(2)).toHaveAttribute('src', `/_embed/${WIDGET_SLUG}`);
  await expect(iframes.nth(3)).toHaveAttribute('src', '/_embed/plain-schedule');

  await expectEmbedTitle(page, 0, 'Innovate to Grow 2025');
  await expectEmbedTitle(page, 1, 'Innovate to Grow 2026');
  await expectEmbedTitle(page, 2, 'Innovate to Grow 2026');
  await expectEmbedTitle(page, 3, 'Innovate to Grow Active');

  expect(new Set(requested)).toEqual(new Set([UUID_A, UUID_B, null]));
});

test('standalone /schedule honours ?schedule_id= and otherwise shows the active schedule', {tag: '@core'}, async ({page}) => {
  const requested = await mockScheduleById(page);

  await page.goto(`/schedule?schedule_id=${UUID_A}`, {waitUntil: 'domcontentloaded'});
  await expect(page.locator(HEADER_TITLE)).toHaveText('Innovate to Grow 2025');
  expect(requested).toContain(UUID_A);
  expect(requested).not.toContain(null);

  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator(HEADER_TITLE)).toHaveText('Innovate to Grow Active');
  expect(requested).toContain(null);
  expect(requested).not.toContain(UUID_B);
});
