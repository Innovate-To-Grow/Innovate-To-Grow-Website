import {describe, expect, it} from 'vitest';

import {
  createProjectGridItems,
  formatTermForProse,
  getEarliestTermYear,
  getPredominantTerm,
  getProjectGridRowHref,
  getProjectGridTeamCode,
  sortProjectGridItems,
  splitStudentNames,
  type ProjectGridRow,
} from '@/features/projects/components/projectGrid';

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

describe('projectGrid helpers', () => {
  it('hides numeric semester suffixes while sorting by their season rank', () => {
    const rows = createProjectGridItems(
      [
        row('2025-2 Fall', 'Fall 2025'),
        row('2025-1 Spring', 'Spring 2025'),
        row('2024-2 Fall', 'Fall 2024'),
      ],
      'semester-sort',
    );

    expect(rows.map((item) => item.semester_label)).toEqual(['2025 Fall', '2025 Spring', '2024 Fall']);

    expect(sortProjectGridItems(rows, 'semester_label', 'asc').map((item) => item.project_title)).toEqual([
      'Fall 2024',
      'Spring 2025',
      'Fall 2025',
    ]);
    expect(sortProjectGridItems(rows, 'semester_label', 'desc').map((item) => item.project_title)).toEqual([
      'Fall 2025',
      'Spring 2025',
      'Fall 2024',
    ]);
  });

  it('orders by class code, then team number, for the "Team number" sort', () => {
    const rows = createProjectGridItems(
      [
        {...row('2026 Spring', 'CSE 2'), class_code: 'CSE', team_number: '2'},
        {...row('2026 Spring', 'CAP 10'), class_code: 'CAP', team_number: '10'},
        {...row('2026 Spring', 'CAP 9'), class_code: 'CAP', team_number: '9'},
      ],
      'team-sort',
    );

    expect(sortProjectGridItems(rows, 'class_code', 'asc').map((item) => item.project_title)).toEqual([
      'CAP 9',
      'CAP 10',
      'CSE 2',
    ]);
  });

  it('formats terms, team codes and student lists for display', () => {
    expect(formatTermForProse('2026-1 Spring')).toBe('Spring 2026');
    expect(formatTermForProse('Summer session')).toBe('Summer session');
    expect(getProjectGridTeamCode({class_code: 'CAP', team_number: '101'})).toBe('CAP 101');
    expect(getProjectGridTeamCode({class_code: '', team_number: '7'})).toBe('7');
    expect(splitStudentNames('Ada Lovelace, Alan Turing; Grace Hopper\n')).toEqual([
      'Ada Lovelace',
      'Alan Turing',
      'Grace Hopper',
    ]);
  });

  it('finds the term most rows share and the earliest year', () => {
    const rows = [row('2026 Spring', 'a'), row('2026-1 Spring', 'b'), row('2025 Fall', 'c'), row('', 'd')];

    expect(getPredominantTerm(rows)).toBe('2026 Spring');
    expect(getPredominantTerm([row('', 'x')])).toBe('');
    expect(getEarliestTermYear([...rows, row('2012 Fall', 'e')])).toBe(2012);
    expect(getEarliestTermYear([row('', 'x')])).toBeNull();
  });

  it('links a row to its current or past project page', () => {
    expect(getProjectGridRowHref({id: 'p-1'}, 'current')).toBe('/projects/p-1');
    expect(getProjectGridRowHref({id: 'p-1'}, 'past')).toBe(`${window.location.origin}/past-projects/project/p-1`);
    expect(getProjectGridRowHref({}, 'past')).toBe('');
  });
});
