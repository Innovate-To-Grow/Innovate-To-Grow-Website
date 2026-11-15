import {describe, expect, it} from 'vitest';

import {
  createProjectGridRowMatcher,
  type ProjectGridRow,
} from '@/features/projects/components/grid/contracts/projectGrid';

const row = (semester_label: string, project_title: string): ProjectGridRow => ({
  semester_label,
  class_code: 'ENGR 120',
  team_number: project_title,
  team_name: project_title,
  project_title,
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
});

describe('createProjectGridRowMatcher', () => {
  const CURRENT_ID = '33333333-3333-4333-8333-333333333333';
  const current = {...row('2026 Fall', 'Irrigation'), id: CURRENT_ID, catalog: 'current' as const, is_presenting: 'Yes'};
  // The same team once its semester is archived: another id, the archive's text, and the current id as its alias.
  const archived = {
    ...row('2026 Fall', 'Irrigation'),
    id: 'archive-1',
    abstract: 'Loaded',
    catalog: 'archive' as const,
    current_project_id: CURRENT_ID,
  };

  it('tells a row by its id or its content', () => {
    const matcher = createProjectGridRowMatcher([{...row('2025 Spring', 'Solar'), id: 'p-1'}]);

    expect(matcher.has({...row('2025 Spring', 'Other'), id: 'p-1'})).toBe(true);
    expect(matcher.has(row('2025 Spring', 'Solar'))).toBe(true);
    expect(matcher.has({...row('2025 Spring', 'Wind'), id: 'p-2'})).toBe(false);
  });

  it('tells a current project from its archive row, whichever of the two it holds', () => {
    expect(createProjectGridRowMatcher([current]).has(archived)).toBe(true);
    expect(createProjectGridRowMatcher([archived]).has(current)).toBe(true);

    const added = createProjectGridRowMatcher([]);
    added.add(archived);
    expect(added.has(current)).toBe(true);

    expect(createProjectGridRowMatcher([archived]).has({...current, id: 'another', project_title: 'Other'})).toBe(false);
  });
});
