import {beforeEach, describe, expect, it, vi} from 'vitest';

import {
  loadProjectDetail,
} from '@/features/projects/hooks/useProjectDetail';
import type {ProjectDetail} from '@/features/projects/api';
import {
  ARCHIVE_PROJECT_ID,
  DASHBOARD_PROJECT_ID,
  HVAC_PROJECT_ID,
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
