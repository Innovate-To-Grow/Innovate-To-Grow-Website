import {describe, expect, it} from 'vitest';

import type {ProjectGridRow} from '@/features/projects/api';
import {
  haveEqualRows,
  projectRowIdentityBase,
  rebaseSubmittedRows,
  rowsNotYetShared,
} from '@/routes/PastProjectsPage/shareRows';

const row = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
  id: 'p1',
  semester_label: '2024-1 Spring',
  class_code: 'CSE',
  team_number: '1',
  team_name: 'Team',
  project_title: 'Project',
  organization: 'Org',
  industry: 'Tech',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

const a = row({id: 'a', project_title: 'A'});
const b = row({id: 'b', project_title: 'B'});
const c = row({id: 'c', project_title: 'C'});
const d = row({id: 'd', project_title: 'D'});
const titles = (rows: ProjectGridRow[]) => rows.map((item) => item.project_title);

describe('haveEqualRows', () => {
  it('compares the stored fields in order', () => {
    expect(haveEqualRows([a, b], [{...a}, {...b}])).toBe(true);
    expect(haveEqualRows([a, b], [b, a])).toBe(false);
    expect(haveEqualRows([a], [a, b])).toBe(false);
    expect(haveEqualRows([a], [{...a, abstract: 'changed'}])).toBe(false);
  });

  it('ignores fields a shared list does not store', () => {
    const withExtra = {...a, __key: 'grid-key'} as ProjectGridRow;
    expect(haveEqualRows([a], [withExtra])).toBe(true);
  });
});

describe('projectRowIdentityBase', () => {
  it('uses the normalized project id', () => {
    expect(projectRowIdentityBase(row({id: '  ABC  '}))).toBe('id:abc');
  });

  it('falls back to the legacy Year-Semester + Class + Team# key without an id', () => {
    expect(projectRowIdentityBase(row({id: undefined, class_code: ' cse ', team_number: '7'}))).toBe(
      'legacy:2024-1 spring\u001fcse\u001f7',
    );
  });

  it('falls back to the full fingerprint when the legacy key is incomplete', () => {
    const first = projectRowIdentityBase(row({id: '', team_number: '', project_title: 'One'}));
    const second = projectRowIdentityBase(row({id: '', team_number: '', project_title: 'Two'}));
    expect(first.startsWith('legacy-fallback:')).toBe(true);
    expect(first).not.toBe(second);
  });
});

describe('rebaseSubmittedRows', () => {
  it('returns the submission unchanged when nothing changed meanwhile', () => {
    expect(rebaseSubmittedRows([a, b], [a, b], [a])).toEqual([a]);
  });

  it('keeps rows someone else added while applying this removal', () => {
    expect(titles(rebaseSubmittedRows([a, b, c], [a, b], [a]))).toEqual(['A', 'C']);
  });

  it('applies only the fields this edit changed onto the current row', () => {
    const current = [{...a, organization: 'Renamed elsewhere'}];
    const rebased = rebaseSubmittedRows(current, [a], [{...a, abstract: 'Edited here'}]);
    expect(rebased).toEqual([{...a, organization: 'Renamed elsewhere', abstract: 'Edited here'}]);
  });

  it('appends an added project once, even when another edit already added it', () => {
    expect(titles(rebaseSubmittedRows([a], [a], [a, d]))).toEqual(['A', 'D']);
    expect(titles(rebaseSubmittedRows([a, d], [a], [a, d]))).toEqual(['A', 'D']);
  });

  it('does not resurrect a row removed elsewhere that this edit left alone', () => {
    expect(titles(rebaseSubmittedRows([a], [a, b], [a, b]))).toEqual(['A']);
  });

  it('keys duplicates by occurrence, so removing one copy keeps the other', () => {
    expect(rebaseSubmittedRows([a, a, b], [a, a, b], [a, b])).toHaveLength(2);
  });

  it('applies a reorder and keeps concurrently added rows after the reordered ones', () => {
    expect(titles(rebaseSubmittedRows([a, b, c, d], [a, b, c], [c, a, b]))).toEqual(['C', 'A', 'B', 'D']);
  });
});

describe('rowsNotYetShared', () => {
  it('drops projects already listed and duplicates within the addition', () => {
    expect(titles(rowsNotYetShared([a], [a, b, {...b}, c]))).toEqual(['B', 'C']);
  });
});
