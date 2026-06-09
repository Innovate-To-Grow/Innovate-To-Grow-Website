// Smoke coverage for the shared Past Projects page. The per-project curation editor was removed,
// so there is no longer any contentEditable behavior to exercise here; these assert that the
// shared route renders the saved snapshot for a visitor and exposes the owner's edit affordances
// only when the share is editable. Desktop engines only (untagged → no @mobile).
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

test.describe('past projects shared page', () => {
  test('renders the saved snapshot with export options for a visitor', async ({page}) => {
    await mockPastProjects(page, pastProjectRows());
    await mockPastProjectShare(page, shareFixture({can_edit: false, note: 'Curated highlights'}));
    await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

    await expect(page.getByText('E2E Shared Results').first()).toBeVisible();
    await expect(page.getByText('Curated highlights').first()).toBeVisible();
    await expect(page.getByText('Adaptive Irrigation Dashboard').first()).toBeVisible();

    // The surviving exports — PDF / Excel / Word — and no per-project notes editor.
    for (const label of ['PDF', 'Excel', 'Microsoft Word']) {
      await expect(page.getByRole('button', {name: label}).first()).toBeVisible();
    }
    await expect(page.getByRole('textbox', {name: 'Project notes'})).toHaveCount(0);

    // A non-owner cannot edit the share's note or name.
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
});
