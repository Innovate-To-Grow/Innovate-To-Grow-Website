import {afterEach, describe, expect, it} from 'vitest';

import {readPersistedDraft, writePersistedDraft} from '@/features/projects/components/builder/draft/curationDraftStorage';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const CURRENT_ID = '33333333-3333-4333-8333-333333333333';
const ARCHIVE_ID = '44444444-4444-4444-8444-444444444444';

const row = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
  id: ARCHIVE_ID,
  semester_label: '2026 Fall',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Irrigation Monitor',
  organization: 'Org A',
  industry: 'Agriculture',
  abstract: 'Abstract-101',
  student_names: 'Ada Lovelace',
  is_presenting: '',
  ...overrides,
});

const storeRows = (rows: unknown[]) =>
  localStorage.setItem('past-projects:builder:draft', JSON.stringify({owner: null, rows, name: '', note: ''}));

describe('curation draft storage', () => {
  afterEach(() => localStorage.clear());

  it('keeps which list a row came from, and the current project an archive row stands in for', () => {
    const current = row({id: CURRENT_ID, catalog: 'current', is_presenting: 'Yes'});
    const standIn = row({catalog: 'archive', current_project_id: CURRENT_ID});
    writePersistedDraft({owner: null, rows: [current, standIn], name: 'Picks', note: ''});

    expect(readPersistedDraft(null).rows).toEqual([current, standIn]);
  });

  it('drops a catalog or a current project id it cannot use, and keeps the row', () => {
    storeRows([
      {...row(), catalog: 'legacy', current_project_id: 'not-a-uuid'},
      {...row({id: CURRENT_ID}), catalog: 42, current_project_id: null},
    ]);

    const rows = readPersistedDraft(null).rows;

    expect(rows).toEqual([row(), row({id: CURRENT_ID})]);
    rows.forEach((stored) => {
      expect(stored).not.toHaveProperty('catalog');
      expect(stored).not.toHaveProperty('current_project_id');
    });
  });
});
