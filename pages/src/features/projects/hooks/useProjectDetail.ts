import {useCallback, useEffect, useMemo, useState} from 'react';
import {fetchProjectDetail, type ProjectDetail} from '@/features/projects/api';
import {
  fetchCurrentSchedule,
  type EventSchedulePayload,
  type ScheduleProjectRow,
  type ScheduleSection,
} from '@/features/events/api';
import {addMinutes} from '@/lib/format';
import {getPredominantTerm} from '../components/grid/contracts/projectGrid';
import {currentScheduleClassLabels, currentScheduleToGridRows} from './useProjectGridData';

/** Where a project page's data came from: this semester's schedule, or the published archive. */
export type ProjectDetailSource = 'current' | 'archive';

/** Where and when a current team presents at the showcase; empty fields are not in the schedule. */
export interface ProjectPresentation {
  /** "Track 2". */
  track: string;
  /** The slot's start, as the schedule page shows it ("1:30"). */
  time: string;
  room: string;
}

export interface ResolvedProjectDetail {
  project: ProjectDetail;
  /** The class's name for its code ("Engineering Capstone" for CAP), when the schedule names it. */
  classLabel: string;
  source: ProjectDetailSource;
  /** Current projects: the team's showcase slot, or null when it is not presenting. Absent for archive projects. */
  presentation?: ProjectPresentation | null;
}

/** 'not-found': every source answered and none has the project. 'failed': a source could not be read. */
export type ProjectDetailError = 'not-found' | 'failed';

const isNotFound = (error: unknown) => (error as {response?: {status?: number}} | null)?.response?.status === 404;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Projects (archive and current) are identified by UUIDs. Anything else in a project URL ("archive", "past", a
 * mangled link) names no project: requesting it would reach one of the list endpoints that share the /projects/
 * prefix and render that list as an empty project page.
 */
export const isProjectId = (value: string) => UUID_PATTERN.test(value);

/** The section, track and slot of a schedule slot id. */
const findSlot = (payload: Partial<EventSchedulePayload>, slotId: string) => {
  for (const section of payload.sections ?? []) {
    for (const track of section.tracks ?? []) {
      const slot = (track.slots ?? []).find((candidate) => candidate.id === slotId);
      if (slot) return {section, track, slot};
    }
  }
  return null;
};

/** A slot's start, as the schedule page shows it: the class's start plus a slot length per earlier slot. */
const slotStart = (section: ScheduleSection, order: number) =>
  section.start_time ? addMinutes(section.start_time, section.slot_minutes * (order - 1)) : '';

/** The showcase slot of a presenting team, whose schedule row has the slot's id. */
const findPresentation = (
  payload: Partial<EventSchedulePayload>,
  scheduleRow: ScheduleProjectRow,
): ProjectPresentation | null => {
  if (!scheduleRow.is_presenting) return null;
  const found = findSlot(payload, scheduleRow.id);
  // Presenting, but listed outside the grid (by its own id at track 0): no slot to name.
  if (!found) return {track: '', time: '', room: ''};
  const {section, track, slot} = found;
  return {track: track.label || `Track ${track.track_number}`, time: slotStart(section, slot.order), room: (track.room ?? '').trim()};
};

/**
 * The current-semester project a Current Projects or Presenting Teams row links to, read back from the schedule
 * payload those lists are built from. The rows link by the schedule's project id (an event CurrentProject, also
 * for teams that are not presenting), which the archive detail endpoint does not know, so the same row mapping
 * is used here: whatever id a row links to resolves to that row.
 */
export const findCurrentScheduleProject = (
  payload: Pick<EventSchedulePayload, 'projects'> & Partial<EventSchedulePayload>,
  projectId: string,
): ResolvedProjectDetail | null => {
  if (!Array.isArray(payload?.projects)) return null;
  const rows = currentScheduleToGridRows(payload);
  const index = rows.findIndex((row) => row.id === projectId);
  if (index < 0) return null;
  const row = rows[index];
  const scheduleRow = payload.projects[index];
  return {
    project: {
      id: projectId,
      project_title: row.project_title,
      team_name: row.team_name,
      team_number: row.team_number,
      organization: row.organization,
      industry: row.industry,
      abstract: row.abstract,
      student_names: row.student_names,
      class_code: row.class_code,
      track: scheduleRow.track || null,
      presentation_order: scheduleRow.order || null,
      // Teams that are not presenting carry no term of their own: they belong to the schedule's semester.
      semester_label: row.semester_label || getPredominantTerm(rows),
    },
    classLabel: currentScheduleClassLabels(payload)[row.class_code] ?? '',
    source: 'current',
    presentation: findPresentation(payload, scheduleRow),
  };
};

/**
 * Loads the project a project page shows. `/projects/:id` is linked from Current Projects (schedule project ids)
 * and by older links to archive projects, so with `includeCurrent` the current schedule is searched first and the
 * archive second; `/past-projects/project/:id` reads the archive only. The error thrown is a 404 only when every
 * source answered and none has the project: if the schedule could not be read, its error is rethrown instead, so
 * the page offers to try again rather than calling the link wrong.
 */
export const loadProjectDetail = async (
  projectId: string,
  {includeCurrent, signal}: {includeCurrent: boolean; signal?: AbortSignal},
): Promise<ResolvedProjectDetail> => {
  let scheduleFailure: {error: unknown} | null = null;
  if (includeCurrent) {
    try {
      const match = findCurrentScheduleProject(await fetchCurrentSchedule(), projectId);
      if (match) return match;
    } catch (error) {
      // A 404 means no schedule is published, so there are no current projects to look in.
      if (!isNotFound(error)) scheduleFailure = {error};
    }
    signal?.throwIfAborted();
  }
  try {
    return {project: await fetchProjectDetail(projectId, signal), classLabel: '', source: 'archive'};
  } catch (error) {
    throw scheduleFailure && isNotFound(error) ? scheduleFailure.error : error;
  }
};

interface ProjectDetailState {
  requestKey: symbol | null;
  result: ResolvedProjectDetail | null;
  error: ProjectDetailError | null;
}

interface ProjectDetailResult {
  result: ResolvedProjectDetail | null;
  loading: boolean;
  error: ProjectDetailError | null;
  retry: () => void;
}

export function useProjectDetail(projectId: string | undefined, includeCurrent: boolean): ProjectDetailResult {
  const [attempt, setAttempt] = useState(0);
  const validId = projectId && isProjectId(projectId) ? projectId : undefined;
  // eslint-disable-next-line react-hooks/exhaustive-deps -- attempt forces a new Symbol so retry() loads again
  const requestKey = useMemo(() => (validId ? Symbol(validId) : null), [validId, includeCurrent, attempt]);
  const [state, setState] = useState<ProjectDetailState>({requestKey: null, result: null, error: null});
  const retry = useCallback(() => setAttempt((count) => count + 1), []);

  useEffect(() => {
    if (!requestKey || !validId) return;
    const controller = new AbortController();
    loadProjectDetail(validId, {includeCurrent, signal: controller.signal})
      .then((result) => {
        if (!controller.signal.aborted) setState({requestKey, result, error: null});
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({requestKey, result: null, error: isNotFound(error) ? 'not-found' : 'failed'});
        }
      });
    return () => controller.abort();
  }, [requestKey, validId, includeCurrent]);

  if (!requestKey) return {result: null, loading: false, error: 'not-found', retry};
  const hasResolved = state.requestKey === requestKey;
  return {
    result: hasResolved ? state.result : null,
    loading: !hasResolved,
    error: hasResolved ? state.error : null,
    retry,
  };
}
