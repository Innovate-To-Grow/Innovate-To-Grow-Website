import {describe, expect, it, vi} from 'vitest';

import {
  createProjectGridItems,
  formatTermForProse,
  getEarliestTermYear,
  getPredominantTerm,
  getProjectGridRowHref,
  getDefaultClassName,
  getDisplayTeamNumber,
  getProjectGridSearchValue,
  getProjectGridTeamCode,
  normalizeSearchText,
  sortProjectGridItems,
  splitStudentNames,
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

  it('names a class by its code the way the schedule does, whatever the case', () => {
    expect(getDefaultClassName('CAP')).toBe('Engineering Capstone');
    expect(getDefaultClassName('CSE')).toBe('Software Engineering Capstone');
    expect(getDefaultClassName('CEE')).toBe('Civil & Environmental Engineering');
    expect(getDefaultClassName(' EngSL ')).toBe('Engineering Service Learning');
    expect(getDefaultClassName('ENGR 120')).toBe('');
    expect(getDefaultClassName(undefined as unknown as string)).toBe('');
  });

  it('formats terms, team codes and student lists for display', () => {
    expect(formatTermForProse('2026-1 Spring')).toBe('Spring 2026');
    expect(formatTermForProse('Summer session')).toBe('Summer session');
    expect(getProjectGridTeamCode({class_code: 'CAP', team_number: '101'})).toBe('CAP 101');
    expect(getProjectGridTeamCode({class_code: '', team_number: '7'})).toBe('7');
    // The 2021 sheets stored the class prefix in the team number: the class code is shown once.
    expect(getProjectGridTeamCode({class_code: 'CAP', team_number: 'CAP01'})).toBe('CAP 01');
    expect(getProjectGridTeamCode({class_code: 'CSE', team_number: 'cse-13'})).toBe('CSE 13');
    expect(getDisplayTeamNumber({class_code: 'CAP', team_number: 'CAP01'})).toBe('01');
    expect(getDisplayTeamNumber({class_code: 'CAP', team_number: 'CAPSTONE'})).toBe('CAPSTONE');
    expect(getDisplayTeamNumber({class_code: 'CAP', team_number: 'CAP'})).toBe('CAP');
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

  it('searches what the page shows: both term formats, the team code with or without its space, the class name', () => {
    const value = getProjectGridSearchValue(
      {...row('2026 Fall', 'In-Air Drop "Shower-Head"'), class_code: 'CAP', team_number: '101', is_presenting: 'Yes'},
      {CAP: 'Engineering Capstone'},
    );

    const shownText = ['2026 fall', 'fall 2026', 'cap 101', 'cap101', 'engineering capstone', '"shower-head"'];
    // Across columns, as the table lists them, and with the term as prose reads it.
    for (const shown of [...shownText, '2026 fall cap 101', 'fall 2026 cap 101']) {
      expect(value).toContain(shown);
    }
    // The hidden Yes/No presenting flag is not part of it.
    expect(value).not.toMatch(/\byes\b/);
    expect(getProjectGridSearchValue({...row('', 'Untitled'), is_presenting: 'No'})).not.toMatch(/\bno\b/);
  });

  it('compares searches without case, accents, curly quotes or repeated spaces', () => {
    expect(normalizeSearchText('  Živanović \u201cShower-Head\u201d   CAP  101 ')).toBe('zivanovic "shower-head" cap 101');
    expect(normalizeSearchText('\u2018Smart\u2019 sensors')).toBe("'smart' sensors");
  });

  it('links a row to its current or past project page', () => {
    expect(getProjectGridRowHref({id: 'p-1'}, 'current')).toBe('/projects/p-1');
    expect(getProjectGridRowHref({id: 'p-1'}, 'past')).toBe(`${window.location.origin}/past-projects/project/p-1`);
    expect(getProjectGridRowHref({}, 'past')).toBe('');
  });
});
