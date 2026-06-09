import {renderHook, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const projectsApiMock = vi.hoisted(() => ({
  fetchAllPastProjects: vi.fn(),
}));

vi.mock('@/features/projects/api', () => projectsApiMock);

import {usePastProjectsData} from '@/features/projects/hooks/usePastProjectsData';

describe('usePastProjectsData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps past projects to sheet rows', async () => {
    projectsApiMock.fetchAllPastProjects.mockResolvedValue([
      {
        id: 'p1',
        track: 2,
        presentation_order: 3,
        semester_label: '2026-1 Spring',
        class_code: 'ENGR 190',
        team_number: '7',
        team_name: 'Team',
        project_title: 'Project',
        organization: 'Org',
        industry: 'Energy',
        abstract: 'Abstract',
        student_names: 'Student',
        is_presenting: true,
      },
      {
        id: 'p2',
        track: null,
        presentation_order: null,
        semester_label: '2025-2 Fall',
        class_code: 'ENGR 191',
        team_number: '8',
        team_name: 'Other',
        project_title: 'Other Project',
        organization: 'Org 2',
        industry: 'Health',
        abstract: 'Other abstract',
        student_names: 'Student 2',
        is_presenting: null,
      },
    ]);

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.rows).toMatchObject([
      {'Year-Semester': '2026 Spring', Track: '2', Order: '3', 'Showcase Participation': 'Yes'},
      {'Year-Semester': '2025 Fall', Track: '', Order: '', 'Showcase Participation': ''},
    ]);
  });

  it('reports load errors', async () => {
    projectsApiMock.fetchAllPastProjects.mockRejectedValue(new Error('archive down'));

    const {result} = renderHook(() => usePastProjectsData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('archive down');
    expect(result.current.rows).toEqual([]);
  });
});
