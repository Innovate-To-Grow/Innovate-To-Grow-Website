import {describe, expect, it, vi} from 'vitest';

import {
  findCurrentScheduleProject,
} from '@/features/projects/hooks/useProjectDetail';
import {currentScheduleToGridRows} from '@/features/projects/hooks/useProjectGridData';
import {getProjectGridRowHref} from '@/features/projects/components/grid/contracts/projectGrid';
import {
  ARCHIVE_PROJECT_ID,
  DASHBOARD_PROJECT_ID,
  HVAC_PROJECT_ID,
  HVAC_SLOT_ID,
  WEED_PROJECT_ID,
  WING_PROJECT_ID,
  currentSchedulePayload,
} from '@/__tests__/features/projects/fixtures/currentSchedule';

const {mockFetchCurrentSchedule, mockFetchProjectDetail} = vi.hoisted(() => ({
  mockFetchCurrentSchedule: vi.fn(),
  mockFetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: (...args: unknown[]) => mockFetchCurrentSchedule(...args),
}));

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: (...args: unknown[]) => mockFetchProjectDetail(...args),
}));
describe('findCurrentScheduleProject', () => {
  it('finds a presenting team by the project id its slot links to, with its class name and term', () => {
    expect(findCurrentScheduleProject(currentSchedulePayload(), HVAC_PROJECT_ID)).toEqual({
      project: {
        id: HVAC_PROJECT_ID,
        project_title: 'ASHRAE HVAC Design Calculations',
        team_name: 'HVAC Regulators',
        team_number: '101',
        organization: 'ASHRAE - Sierra Delta',
        industry: 'Energy',
        abstract: expect.stringMatching(/^This project aimed to design a complete HVAC system/),
        student_names: 'Brian Arroyo, Joel Gonzalez, Kyle On, Manuel Cruz Cavero',
        class_code: 'CAP',
        track: 1,
        presentation_order: 1,
        semester_label: '2026 Spring',
      },
      classLabel: 'Engineering Capstone',
      source: 'current',
      presentation: {track: 'Track 1', time: '1:00', room: 'Glacier 165'},
    });
  });

  it("gives a presenting team its slot's start: the class's start plus a slot length per earlier slot", () => {
    expect(findCurrentScheduleProject(currentSchedulePayload(), WEED_PROJECT_ID)?.presentation).toEqual({
      track: 'Track 1',
      time: '1:30',
      room: 'Glacier 165',
    });
    expect(findCurrentScheduleProject(currentSchedulePayload(), DASHBOARD_PROJECT_ID)?.presentation).toEqual({
      track: 'Track 6',
      time: '1:00',
      room: 'Glacier 140',
    });
  });

  it('leaves out an empty room, and names no slot for a presenting team listed outside the grid', () => {
    const payload = currentSchedulePayload();
    payload.sections[0].tracks[0].room = '  ';
    expect(findCurrentScheduleProject(payload, HVAC_PROJECT_ID)?.presentation).toEqual({
      track: 'Track 1',
      time: '1:00',
      room: '',
    });

    payload.projects[3] = {...payload.projects[3], is_presenting: true};
    expect(findCurrentScheduleProject(payload, WING_PROJECT_ID)?.presentation).toEqual({track: '', time: '', room: ''});
  });

  it("finds a team that is not presenting by its own id and gives it the schedule's term", () => {
    const found = findCurrentScheduleProject(currentSchedulePayload(), WING_PROJECT_ID);

    expect(found?.project).toMatchObject({
      project_title: 'Distributed-Flapping Wing with Glide-Lock Mechanism',
      track: null,
      presentation_order: null,
      semester_label: '2026 Spring',
    });
    expect(found?.classLabel).toBe('Engineering Capstone');
    expect(found?.presentation).toBeNull();
  });

  it('resolves every project link the current-projects list renders', () => {
    const payload = currentSchedulePayload();
    const linked = currentScheduleToGridRows(payload).filter((row) => row.id);

    expect(linked).toHaveLength(payload.projects.length);
    linked.forEach((row) => {
      const id = decodeURIComponent(getProjectGridRowHref(row, 'current').replace('/projects/', ''));
      expect(findCurrentScheduleProject(payload, id)?.project.project_title).toBe(row.project_title);
    });
  });

  it('does not answer for slot ids, archive ids or a payload without projects', () => {
    expect(findCurrentScheduleProject(currentSchedulePayload(), HVAC_SLOT_ID)).toBeNull();
    expect(findCurrentScheduleProject(currentSchedulePayload(), ARCHIVE_PROJECT_ID)).toBeNull();
    expect(findCurrentScheduleProject({} as never, HVAC_PROJECT_ID)).toBeNull();
  });

  it('leaves the class name empty when the schedule does not name the class', () => {
    const payload = {...currentSchedulePayload(), sections: undefined};
    // Without sections there are no slot links: only teams that are not presenting have ids.
    expect(findCurrentScheduleProject(payload, WING_PROJECT_ID)?.classLabel).toBe('');
  });
});
