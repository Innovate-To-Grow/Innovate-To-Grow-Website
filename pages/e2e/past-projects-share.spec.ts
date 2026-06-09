// Owner editing of the share-level rich-text Note on a shared Past Projects page. The per-project
// curation editor was removed, but the share Note is itself a RichTextDetailEditor, so the same
// real-browser contentEditable + Selection behaviors jsdom cannot reproduce still need coverage:
// typing must not reset the caret (the FE-1 focus guard), and a highlight must toggle on and back
// off without re-selecting (real <mark> wrap/re-select + the sync effect not rewriting the user's
// own edit). Desktop engines only (untagged → no @mobile).
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

const noteEditor = (page: import('@playwright/test').Page) =>
  page.getByRole('textbox', {name: 'Note'}).first();

test.describe('past projects shared page', () => {
  test('renders the saved snapshot with export options for a visitor', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture({can_edit: false, note: 'Curated highlights'}));
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await expect(page.getByText('E2E Shared Results').first()).toBeVisible();
    await expect(page.getByText('Curated highlights').first()).toBeVisible();
    await expect(page.getByText('Adaptive Irrigation Dashboard').first()).toBeVisible();

    // The surviving exports — PDF / Excel / Word — and no editable note for a non-owner.
    for (const label of ['PDF', 'Excel', 'Microsoft Word']) {
      await expect(page.getByRole('button', {name: label}).first()).toBeVisible();
    }
    // A non-owner sees the note read-only: no editor textbox and no formatting toolbar.
    await expect(page.getByRole('textbox', {name: 'Note'})).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Highlight'})).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Bold'})).toHaveCount(0);
    await expect(page.getByRole('button', {name: /edit note/i})).toHaveCount(0);
    await expect(page.getByRole('button', {name: /edit name/i})).toHaveCount(0);
  });

  test('shows the note and name edit affordances to an owner', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture({can_edit: true}));
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await expect(page.getByRole('button', {name: /edit note/i}).first()).toBeVisible();
    await expect(page.getByRole('button', {name: /edit name/i}).first()).toBeVisible();
  });

  test('owner can type into the note and the text persists in order', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture({can_edit: true}));
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await page.getByRole('button', {name: /edit note/i}).first().click();
    const editor = noteEditor(page);
    await editor.click();
    await page.keyboard.type('Hello world');

    // A caret that reset to the start on each keystroke would interleave/reverse the text.
    await expect(editor).toContainText('Hello world');
  });

  test('owner can toggle a note highlight on and back off without re-selecting', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture({can_edit: true}));
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await page.getByRole('button', {name: /edit note/i}).first().click();
    const editor = noteEditor(page);
    await editor.click();
    await page.keyboard.type('Highlight me');
    await page.keyboard.press('ControlOrMeta+a');

    const highlight = page.getByRole('button', {name: 'Highlight'}).first();
    await highlight.click();
    await expect(editor.locator('mark')).toHaveCount(1);

    // The second click must find the still-selected highlight and remove it. This only works
    // because applyHighlight re-selects the <mark> and the sync effect does not rewrite innerHTML
    // for the user's own edit (which would have collapsed the selection).
    await highlight.click();
    await expect(editor.locator('mark')).toHaveCount(0);
  });
});
