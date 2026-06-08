// Owner editing of per-project curation notes on a shared Past Projects page. The rich note
// editor relies on real-browser contentEditable + Selection behavior that jsdom cannot reproduce:
// typing must not reset the caret (FE-1 focus guard), and a highlight must toggle on and back off
// without re-selecting (real <mark> wrap/re-select + the sync effect not rewriting the user's own
// edit). These run on the desktop engines only (untagged → no @mobile).
import type {PastProjectShare} from '../src/features/projects/api';
import {mockPastProjects, mockPastProjectShare, pastProjectRows} from './helpers';
import {expect, test} from './fixtures';

const SHARE_ID = 'share-e2e-1';

function shareFixture(overrides: Partial<PastProjectShare> = {}): PastProjectShare {
  return {
    id: SHARE_ID,
    name: 'E2E Shared Results',
    rows: [
      {
        semester_label: '2025 Fall',
        class_code: 'CSE 120',
        team_number: '7',
        team_name: 'Team Helix',
        project_title: 'Adaptive Irrigation Dashboard',
        organization: 'Acme Corp',
        industry: 'Agriculture',
        abstract: 'A dashboard that optimizes irrigation schedules.',
        student_names: 'Ada Lovelace, Alan Turing',
        is_presenting: 'Yes',
        curation: '',
        ...overrides.rows?.[0],
      },
    ],
    note: '',
    details_text: '',
    share_url: `/past-projects/${SHARE_ID}`,
    can_edit: true,
    created_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

// The desktop table and the mobile cards both render a copy of every row, so scope the per-row
// curation editor to the desktop table to get a single match.
const desktopCurationEditor = (page: import('@playwright/test').Page) =>
  page.locator('.project-grid-table-wrap').getByRole('textbox', {name: 'Project notes'});

test.describe('past projects per-project curation editor', () => {
  test('owner can type a curation note and the text persists in order', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture());
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    const editor = desktopCurationEditor(page);
    await editor.click();
    await page.keyboard.type('Hello world');

    // A caret that reset to the start on each keystroke would interleave/reverse the text.
    await expect(editor).toContainText('Hello world');
  });

  test('owner can toggle a highlight on and back off without re-selecting', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture());
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    const editor = desktopCurationEditor(page);
    await editor.click();
    await page.keyboard.type('Highlight me');
    await page.keyboard.press('ControlOrMeta+a');

    const toolbar = page.locator('.project-grid-table-wrap').getByRole('button', {name: 'Highlight'}).first();
    await toolbar.click();
    await expect(editor.locator('mark')).toHaveCount(1);

    // The second click must find the still-selected highlight and remove it. This only works
    // because applyHighlight re-selects the <mark> and the sync effect does not rewrite innerHTML
    // for the user's own edit (which would have collapsed the selection).
    await toolbar.click();
    await expect(editor.locator('mark')).toHaveCount(0);
  });

  test('a non-owner shared view shows saved notes read-only with no toolbar', async ({page}) => {
    await mockPastProjectShare(
      page,
      shareFixture({can_edit: false, rows: [{curation: 'Read only note text'} as PastProjectShare['rows'][number]]}),
    );
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await expect(page.getByText('Read only note text').first()).toBeVisible();
    await expect(page.getByRole('textbox', {name: 'Project notes'})).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Highlight'})).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Bold'})).toHaveCount(0);
  });
});
