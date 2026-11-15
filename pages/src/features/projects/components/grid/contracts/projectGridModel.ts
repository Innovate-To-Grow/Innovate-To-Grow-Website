import type {ProjectGridRow} from '@/features/projects/api';
import {formatSemesterLabel} from '@/lib/format';

export type ProjectGridColumnKey = keyof ProjectGridRow;
export type ProjectGridSortDirection = 'asc' | 'desc';

export interface ProjectGridColumn {
  key: ProjectGridColumnKey;
  label: string;
}

export interface ProjectGridItem extends ProjectGridRow {
  __key: string;
}

/**
 * Columns of the current-projects table. Cells are composite: "Team" shows the class code and team number,
 * and "Project" shows the title (linked to the project page) with the team name under it.
 */
export const PROJECT_GRID_COLUMNS: ProjectGridColumn[] = [
  {key: 'class_code', label: 'Team'},
  {key: 'project_title', label: 'Project'},
  {key: 'organization', label: 'Organization'},
  {key: 'industry', label: 'Industry'},
];

/** Columns of the past-project tables: "Term" shows the semester with the class code and team number under it. */
export const PAST_PROJECT_GRID_COLUMNS: ProjectGridColumn[] = [
  {key: 'semester_label', label: 'Term'},
  {key: 'project_title', label: 'Project'},
  {key: 'organization', label: 'Organization'},
  {key: 'industry', label: 'Industry'},
];

/**
 * A team number as it reads after its class code: "01" for "CAP01" in class CAP (the 2021 sheets stored the class
 * prefix in the team number), otherwise the number as stored.
 */
export const getDisplayTeamNumber = ({class_code, team_number}: Pick<ProjectGridRow, 'class_code' | 'team_number'>) => {
  const number = (team_number ?? '').trim();
  const code = (class_code ?? '').trim();
  if (!code || number.slice(0, code.length).toUpperCase() !== code.toUpperCase()) return number;
  const rest = number.slice(code.length).replace(/^[\s-]+/, '');
  return /^\d/.test(rest) ? rest : number;
};

/**
 * Class names by code, as the event schedule names its sections when nothing overrides them (the backend's
 * schedule_sync SECTION_DEFAULTS). Archive projects carry only the code; the schedule's own names win for current
 * ones.
 */
const DEFAULT_CLASS_NAMES: Record<string, string> = {
  CAP: 'Engineering Capstone',
  CEE: 'Civil & Environmental Engineering',
  CSE: 'Software Engineering Capstone',
  ENGSL: 'Engineering Service Learning',
};

/** "Engineering Capstone" for "CAP" (any case), or '' for a class the site does not name. */
export const getDefaultClassName = (classCode: string) =>
  DEFAULT_CLASS_NAMES[(classCode ?? '').trim().toUpperCase()] ?? '';

/** "CAP 101": the class code and team number a team is known by. */
export const getProjectGridTeamCode = (row: Pick<ProjectGridRow, 'class_code' | 'team_number'>) =>
  [row.class_code ?? '', getDisplayTeamNumber(row)].map((value) => value.trim()).filter(Boolean).join(' ');

/** "2026 Spring" (how terms are listed in tables) to "Spring 2026" (how they read in a sentence). */
export const formatTermForProse = (label: string) => {
  const normalized = formatSemesterLabel(label ?? '').trim();
  const match = normalized.match(/^(\d{4})\s+(.+)$/);
  return match ? `${match[2]} ${match[1]}` : normalized;
};

/** The term most rows belong to (rows with no term are ignored), for a page's meta line. */
export const getPredominantTerm = (rows: Array<Pick<ProjectGridRow, 'semester_label'>>) => {
  const counts = new Map<string, number>();
  rows.forEach((row) => {
    const term = formatSemesterLabel(row.semester_label ?? '').trim();
    if (term) counts.set(term, (counts.get(term) ?? 0) + 1);
  });
  let best = '';
  let bestCount = 0;
  counts.forEach((count, term) => {
    if (count > bestCount) {
      best = term;
      bestCount = count;
    }
  });
  return best;
};

/** The earliest year any row's term names, e.g. for "920 projects since 2012". */
export const getEarliestTermYear = (rows: Array<Pick<ProjectGridRow, 'semester_label'>>) => {
  let earliest: number | null = null;
  rows.forEach((row) => {
    const match = (row.semester_label ?? '').match(/^\s*(\d{4})/);
    if (match) {
      const year = Number(match[1]);
      earliest = earliest === null ? year : Math.min(earliest, year);
    }
  });
  return earliest;
};

/** Splits a "Name One, Name Two" student list into names. */
export const splitStudentNames = (value: string) =>
  (value ?? '')
    .split(/[,;\n]/)
    .map((name) => name.trim())
    .filter(Boolean);

// `id` is deliberately excluded from the content fingerprint so equivalent rows from archive and
// AI search sources still deduplicate when one source lacks an id. The id remains on the row for
// the per-project Individual Link.
export const createProjectGridFingerprint = (row: ProjectGridRow) =>
  JSON.stringify([
    formatSemesterLabel(row.semester_label),
    row.class_code,
    row.team_number,
    row.team_name,
    row.project_title,
    row.organization,
    row.industry,
    row.abstract,
    row.student_names,
    row.is_presenting,
  ]);

/** The ids a row is known by: its own, and the current-semester project's an archive row stands in for. */
export const getProjectRowIds = (row: ProjectGridRow) =>
  [row.id, row.current_project_id].filter((id): id is string => Boolean(id));

/**
 * Tells whether a row is one of `rows`: the same project id, or the same content. The fingerprint alone is not
 * enough, since a compact archive row and the hydrated copy of the same project differ in abstract and students.
 * A current-semester project and the archive row that stands in for it once its semester is archived are the same
 * project: the archive row names the current id in `current_project_id`, so a draft that holds either matches.
 */
export const createProjectGridRowMatcher = (rows: ProjectGridRow[]) => {
  const ids = new Set<string>();
  const fingerprints = new Set<string>();
  const add = (row: ProjectGridRow) => {
    getProjectRowIds(row).forEach((id) => ids.add(id));
    fingerprints.add(createProjectGridFingerprint(row));
  };
  rows.forEach(add);
  return {
    add,
    has: (row: ProjectGridRow) =>
      getProjectRowIds(row).some((id) => ids.has(id)) || fingerprints.has(createProjectGridFingerprint(row)),
  };
};

export const createProjectGridItems = (rows: ProjectGridRow[], namespace: string): ProjectGridItem[] =>
  rows.map((row, index) => {
    const gridRow = {
      ...row,
      semester_label: formatSemesterLabel(row.semester_label),
    };

    return {
      ...gridRow,
      __key: `${namespace}-${index}-${createProjectGridFingerprint(gridRow)}`,
    };
  });

export const stripProjectGridItem = (row: ProjectGridItem): ProjectGridRow => {
  const {__key, ...gridRow} = row;
  void __key;
  return gridRow;
};
