import {describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}));
const authApiMock = vi.hoisted(() => ({
  delete: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}));
const mockGetAccessToken = vi.hoisted(() => vi.fn());
const mockIsDefinitiveAuthFailure = vi.hoisted(() =>
  vi.fn((error: unknown) =>
    Boolean(
      error &&
        typeof error === 'object' &&
        (error as {definitive?: boolean}).definitive,
    ),
  ),
);

vi.mock('@/lib/api', () => ({api: apiMock}));
// The shared test setup stubs the archive search; this file tests the real one.
vi.unmock('@/features/projects/api/archive');
vi.mock('@/features/auth', () => ({
  authApi: authApiMock,
  getAccessToken: mockGetAccessToken,
  isDefinitiveAuthFailure: mockIsDefinitiveAuthFailure,
}));

import {
  compactProjectToGridRow,
  needsProjectGridHydration,
  scheduleProjectToGridRow,
  toProjectGridRow,
  type ProjectTableRow,
} from '@/features/projects/api';
const makeTableRow = (overrides: Partial<ProjectTableRow> = {}): ProjectTableRow => ({
  id: 'project-1',
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Team A',
  project_title: 'Project A',
  organization: 'Org A',
  industry: 'Energy',
  abstract: 'An abstract',
  student_names: 'Alex',
  track: null,
  presentation_order: null,
  ...overrides,
});

describe('project grid row mappers', () => {
  it('maps a table row to a grid row and formats the semester label', () => {
    expect(toProjectGridRow(makeTableRow({is_presenting: undefined}))).toMatchObject({
      id: 'project-1',
      semester_label: '2025 Spring',
      is_presenting: '',
    });
    expect(toProjectGridRow(makeTableRow({is_presenting: true})).is_presenting).toBe('Yes');
    expect(toProjectGridRow(makeTableRow({is_presenting: false})).is_presenting).toBe('No');
  });

  it('maps a schedule row without an id and normalizes is_presenting', () => {
    const scheduleRow = {
      id: 'schedule-1',
      track: 1,
      order: 2,
      year_semester: '2025-1 Spring',
      class_code: 'CAP',
      team_number: '101',
      team_name: 'Team A',
      project_title: 'Project A',
      organization: 'Org A',
      industry: 'Energy',
      abstract: 'An abstract',
      student_names: 'Alex',
      is_presenting: true,
      tooltip: '',
    };
    expect(scheduleProjectToGridRow(scheduleRow)).toMatchObject({
      semester_label: '2025 Spring',
      is_presenting: 'Yes',
    });
    expect(scheduleProjectToGridRow(scheduleRow)).not.toHaveProperty('id');
    expect(scheduleProjectToGridRow({...scheduleRow, is_presenting: false}).is_presenting).toBe('No');
  });

  it('keeps the student names the archive sends, so a search finds a team by its members', () => {
    const compact = {
      id: 'project-1',
      semester_label: '2025-1 Spring',
      class_code: 'CAP',
      team_number: '101',
      team_name: 'Team A',
      project_title: 'Project A',
      organization: 'Org A',
      industry: 'Energy',
      student_names: 'Brian Arroyo, Joel Gonzalez',
      track: null,
      presentation_order: null,
    };
    const row = compactProjectToGridRow(compact);

    expect(row).toMatchObject({abstract: '', student_names: 'Brian Arroyo, Joel Gonzalez'});
    // The abstract still has to be loaded from the detail endpoint.
    expect(needsProjectGridHydration(row)).toBe(true);
    expect(needsProjectGridHydration({...row, abstract: 'Loaded'})).toBe(false);
    expect(needsProjectGridHydration({...row, id: undefined})).toBe(false);
  });

  it('maps a compact archive row with empty detail fields', () => {
    expect(
      compactProjectToGridRow({
        id: 'project-1',
        semester_label: '2025-1 Spring',
        class_code: 'CAP',
        team_number: '101',
        team_name: 'Team A',
        project_title: 'Project A',
        organization: 'Org A',
        industry: 'Energy',
        track: null,
        presentation_order: null,
      }),
    ).toEqual({
      id: 'project-1',
      semester_label: '2025 Spring',
      class_code: 'CAP',
      team_number: '101',
      team_name: 'Team A',
      project_title: 'Project A',
      organization: 'Org A',
      industry: 'Energy',
      abstract: '',
      student_names: '',
      is_presenting: '',
    });
  });
});
