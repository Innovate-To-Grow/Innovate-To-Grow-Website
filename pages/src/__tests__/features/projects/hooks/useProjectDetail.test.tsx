import {act, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  findCurrentScheduleProject,
  loadProjectDetail,
  useProjectDetail,
} from '@/features/projects/hooks/useProjectDetail';
import {currentScheduleToGridRows} from '@/features/projects/hooks/useProjectGridData';
import {getProjectGridRowHref} from '@/features/projects/components/projectGrid';
import type {ProjectDetail} from '@/features/projects/api';
import {
  ARCHIVE_PROJECT_ID,
  DASHBOARD_PROJECT_ID,
  HVAC_PROJECT_ID,
  HVAC_SLOT_ID,
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

const notFound = () => Object.assign(new Error('Request failed with status code 404'), {response: {status: 404}});
const serverError = () => Object.assign(new Error('Request failed with status code 502'), {response: {status: 502}});

const archiveProject: ProjectDetail = {
  id: ARCHIVE_PROJECT_ID,
  project_title: 'ASHRAE HVAC Design Calculations',
  team_name: 'HVAC Regulators',
  team_number: '101',
  organization: 'ASHRAE - Sierra Delta',
  industry: 'Energy',
  abstract: 'Archive abstract.',
  student_names: 'Brian Arroyo, Joel Gonzalez',
  class_code: 'CAP',
  track: 1,
  presentation_order: 1,
  semester_label: '2026-1 Spring',
};

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
    });
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

describe('loadProjectDetail', () => {
  beforeEach(() => {
    mockFetchCurrentSchedule.mockReset().mockResolvedValue(currentSchedulePayload());
    mockFetchProjectDetail.mockReset().mockRejectedValue(notFound());
  });

  it('reads a current project from the schedule without asking the archive', async () => {
    const result = await loadProjectDetail(DASHBOARD_PROJECT_ID, {includeCurrent: true});

    expect(result.source).toBe('current');
    expect(result.classLabel).toBe('Software Engineering Capstone');
    expect(result.project.project_title).toBe('Sustainability Dashboard');
    expect(mockFetchProjectDetail).not.toHaveBeenCalled();
  });

  it('falls back to the archive for ids the schedule does not have', async () => {
    mockFetchProjectDetail.mockResolvedValue(archiveProject);
    const signal = new AbortController().signal;

    await expect(loadProjectDetail(ARCHIVE_PROJECT_ID, {includeCurrent: true, signal})).resolves.toEqual({
      project: archiveProject,
      classLabel: '',
      source: 'archive',
    });
    expect(mockFetchProjectDetail).toHaveBeenCalledWith(ARCHIVE_PROJECT_ID, signal);
  });

  it('reads only the archive for past-project pages', async () => {
    mockFetchProjectDetail.mockResolvedValue(archiveProject);

    await expect(loadProjectDetail(ARCHIVE_PROJECT_ID, {includeCurrent: false})).resolves.toMatchObject({
      source: 'archive',
    });
    expect(mockFetchCurrentSchedule).not.toHaveBeenCalled();
  });

  it('reports not found when no schedule is published and the archive has no such project', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(notFound());

    await expect(loadProjectDetail('missing', {includeCurrent: true})).rejects.toMatchObject({
      response: {status: 404},
    });
  });

  it('reports the schedule failure, not a missing project, when the schedule could not be read', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(serverError());

    await expect(loadProjectDetail(HVAC_PROJECT_ID, {includeCurrent: true})).rejects.toMatchObject({
      response: {status: 502},
    });
  });

  it('still shows an archive project when the schedule could not be read', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(serverError());
    mockFetchProjectDetail.mockResolvedValue(archiveProject);

    await expect(loadProjectDetail(ARCHIVE_PROJECT_ID, {includeCurrent: true})).resolves.toMatchObject({
      source: 'archive',
    });
  });

  it('passes on an archive failure that is not a 404', async () => {
    mockFetchProjectDetail.mockRejectedValue(serverError());

    await expect(loadProjectDetail(ARCHIVE_PROJECT_ID, {includeCurrent: true})).rejects.toMatchObject({
      response: {status: 502},
    });
  });

  it('does not ask the archive once the page has moved on', async () => {
    const controller = new AbortController();
    mockFetchCurrentSchedule.mockImplementation(async () => {
      controller.abort();
      return currentSchedulePayload();
    });

    await expect(
      loadProjectDetail(ARCHIVE_PROJECT_ID, {includeCurrent: true, signal: controller.signal}),
    ).rejects.toThrow();
    expect(mockFetchProjectDetail).not.toHaveBeenCalled();
  });
});

describe('useProjectDetail', () => {
  beforeEach(() => {
    mockFetchCurrentSchedule.mockReset().mockResolvedValue(currentSchedulePayload());
    mockFetchProjectDetail.mockReset().mockRejectedValue(notFound());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads a current project', async () => {
    const {result} = renderHook(() => useProjectDetail(HVAC_PROJECT_ID, true));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.result?.project.project_title).toBe('ASHRAE HVAC Design Calculations');
  });

  it('says not found only when no source has the project', async () => {
    const {result} = renderHook(() => useProjectDetail(ARCHIVE_PROJECT_ID, true));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('not-found');
    expect(result.current.result).toBeNull();
  });

  it('says the load failed and loads again on retry', async () => {
    mockFetchCurrentSchedule.mockRejectedValueOnce(serverError());
    const {result} = renderHook(() => useProjectDetail(HVAC_PROJECT_ID, true));

    await waitFor(() => expect(result.current.error).toBe('failed'));

    act(() => result.current.retry());
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.result?.source).toBe('current');
    expect(mockFetchCurrentSchedule).toHaveBeenCalledTimes(2);
  });

  it('treats a missing id as not found without loading anything', () => {
    const {result} = renderHook(() => useProjectDetail(undefined, true));

    expect(result.current).toMatchObject({result: null, loading: false, error: 'not-found'});
    expect(mockFetchCurrentSchedule).not.toHaveBeenCalled();
  });

  it('ignores a response that lands after unmount', async () => {
    let resolve!: (value: unknown) => void;
    mockFetchCurrentSchedule.mockReturnValue(new Promise((res) => (resolve = res)));
    const {unmount} = renderHook(() => useProjectDetail(HVAC_PROJECT_ID, true));
    unmount();

    await act(async () => {
      resolve(currentSchedulePayload());
    });
    expect(mockFetchProjectDetail).not.toHaveBeenCalled();
  });
});
