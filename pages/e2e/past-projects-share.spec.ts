// Owner editing on a shared Past Projects page. The rich detail editor relies on real-browser
// contentEditable + Selection behavior that jsdom cannot reproduce: typing must not reset the
// caret (M2), and a highlight must toggle on and back off without re-selecting (M2 echo-skip +
// M3 <mark> wrap/re-select). These run on the desktop engines only (untagged → no @mobile).
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
      },
    ],
    note: '',
    details_text: 'Highlight this detail',
    share_url: `/past-projects/${SHARE_ID}`,
    can_edit: true,
    created_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

test.describe('past projects share detail editor', () => {
  test('owner can edit the detail and the typed text persists in order', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture());
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await page.getByRole('button', {name: /edit past projects detail/i}).click();
    const editor = page.getByRole('textbox', {name: 'Past Projects Detail'});
    await editor.click();
    await page.keyboard.press('ControlOrMeta+a');
    await page.keyboard.press('Delete');
    await page.keyboard.type('Hello world');

    // A caret that reset to the start on each keystroke would interleave/reverse the text.
    await expect(editor).toContainText('Hello world');
  });

  test('owner can toggle a highlight on and back off without re-selecting', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture());
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await page.getByRole('button', {name: /edit past projects detail/i}).click();
    const editor = page.getByRole('textbox', {name: 'Past Projects Detail'});
    await editor.click();
    await page.keyboard.press('ControlOrMeta+a');

    await page.getByRole('button', {name: 'Highlight'}).click();
    await expect(editor.locator('mark')).toHaveCount(1);

    // The second click must find the still-selected highlight and remove it. This only works
    // because applyHighlight re-selects the <mark> and the sync effect does not rewrite
    // innerHTML for the user's own edit (which would have collapsed the selection).
    await page.getByRole('button', {name: 'Highlight'}).click();
    await expect(editor.locator('mark')).toHaveCount(0);
  });

  test('a non-owner shared view shows the detail read-only with no toolbar', async ({page}) => {
    await mockPastProjectShare(page, shareFixture({can_edit: false, details_text: 'Read only detail text'}));
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await expect(page.getByText('Read only detail text')).toBeVisible();
    await expect(page.getByRole('button', {name: 'Highlight'})).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Bold'})).toHaveCount(0);
  });
});
