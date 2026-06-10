import {describe, expect, it} from 'vitest';

import {
  createProjectGridItems,
  sortProjectGridItems,
  type ProjectGridRow,
} from '../projectGrid';

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
});
