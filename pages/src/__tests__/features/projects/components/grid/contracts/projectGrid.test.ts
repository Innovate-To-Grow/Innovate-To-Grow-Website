import {describe, expect, it, vi} from 'vitest';

import {
  createProjectGridItems,
  sortProjectGridItems,
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

  it('sorts without building a collator per comparison, in natural, case-insensitive order', () => {
    const titles = ['beta 10', 'Alpha', 'beta 9', 'Éclair', 'alpha 2', 'Delta'];
    const rows = createProjectGridItems(titles.map((title) => row('2026 Spring', title)), 'collator');
    const localeCompare = vi.spyOn(String.prototype, 'localeCompare');
    try {
      expect(sortProjectGridItems(rows, 'project_title', 'asc').map((item) => item.project_title)).toEqual([
        'Alpha',
        'alpha 2',
        'beta 9',
        'beta 10',
        'Delta',
        'Éclair',
      ]);
      // localeCompare with options constructs an ICU collator on every call: ~120 ms per 920-row sort at 4x CPU.
      expect(localeCompare).not.toHaveBeenCalled();
    } finally {
      localeCompare.mockRestore();
    }
  });

  it('lists the teams of a term by team number, as numbers, whichever way the terms run', () => {
    // The archive arrives with team numbers ordered as text: 1, 10, 2.
    const team = (semester: string, classCode: string, teamNumber: string) => ({
      ...row(semester, `${semester} ${classCode} ${teamNumber}`),
      class_code: classCode,
      team_number: teamNumber,
    });
    const rows = createProjectGridItems(
      [
        team('2019 Spring', 'CSE', '1'),
        team('2019 Spring', 'CSE', '10'),
        team('2019 Spring', 'CSE', '2'),
        team('2019 Spring', 'CAP', '3'),
        team('2021 Spring', 'CAP', 'CAP10'),
        team('2021 Spring', 'CAP', 'CAP02'),
      ],
      'team-order',
    );

    expect(sortProjectGridItems(rows, 'semester_label', 'desc').map((item) => item.project_title)).toEqual([
      '2021 Spring CAP CAP02',
      '2021 Spring CAP CAP10',
      '2019 Spring CAP 3',
      '2019 Spring CSE 1',
      '2019 Spring CSE 2',
      '2019 Spring CSE 10',
    ]);
    expect(sortProjectGridItems(rows, 'semester_label', 'asc').map((item) => item.project_title).slice(0, 4)).toEqual([
      '2019 Spring CAP 3',
      '2019 Spring CSE 1',
      '2019 Spring CSE 2',
      '2019 Spring CSE 10',
    ]);
  });

  it('breaks ties on the sorted column by team number, in either direction, not by the order rows arrived in', () => {
    const team = (class_code: string, team_number: string, organization: string): ProjectGridRow => ({
      ...row('2026 Fall', `${class_code} ${team_number}`),
      class_code,
      team_number,
      organization,
    });
    // As the schedule sends them: presenting teams (slots) first, the others after.
    const items = createProjectGridItems(
      [team('CAP', '212', 'BART'), team('CSE', '418', 'Agrecom'), team('CAP', '122', 'BART'), team('CAP', '133', 'Agrecom')],
      'ties',
    );
    const order = (direction: 'asc' | 'desc') =>
      sortProjectGridItems(items, 'organization', direction).map((item) => `${item.class_code} ${item.team_number}`);

    expect(order('asc')).toEqual(['CAP 133', 'CSE 418', 'CAP 122', 'CAP 212']);
    // Only the organizations reverse; each one's teams keep team-number order.
    expect(order('desc')).toEqual(['CAP 122', 'CAP 212', 'CAP 133', 'CSE 418']);
  });
});
