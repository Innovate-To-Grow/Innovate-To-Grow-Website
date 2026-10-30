import type {ProjectGridRow, ProjectTableRow} from '@/features/projects/api';
import {formatSemesterLabel} from '@/lib/format';

export type {ProjectGridRow} from '@/features/projects/api';

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

/** Which page a project title links to: the current-projects detail route or the past-projects one. */
export type ProjectGridLinkScope = 'current' | 'past';

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

const SEMESTER_SEASON_RANKS: Record<string, number> = {
  spring: 1,
  fall: 2,
};

const semesterSortKey = (value: string) => {
  const normalized = value.trim();
  const match = normalized.match(/^(\d{4})(?:-(\d+))?\s+(.+)$/);
  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const explicitSeasonRank = match[2] ? Number(match[2]) : undefined;
  const seasonName = match[3].trim().toLowerCase();
  const seasonRank = explicitSeasonRank ?? SEMESTER_SEASON_RANKS[seasonName];

  if (!Number.isFinite(year) || !Number.isFinite(seasonRank)) {
    return null;
  }

  return {year, seasonRank};
};

export const toProjectGridRow = (project: ProjectTableRow): ProjectGridRow => ({
  id: project.id,
  semester_label: formatSemesterLabel(project.semester_label),
  class_code: project.class_code,
  team_number: project.team_number,
  team_name: project.team_name,
  project_title: project.project_title,
  organization: project.organization,
  industry: project.industry,
  abstract: project.abstract,
  student_names: project.student_names,
  is_presenting: project.is_presenting == null ? '' : project.is_presenting ? 'Yes' : 'No',
});

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

/**
 * Tells whether a row is one of `rows`: the same project id, or the same content. The fingerprint alone is not
 * enough, since a compact archive row and the hydrated copy of the same project differ in abstract and students.
 */
export const createProjectGridRowMatcher = (rows: ProjectGridRow[]) => {
  const ids = new Set<string>();
  const fingerprints = new Set<string>();
  const add = (row: ProjectGridRow) => {
    if (row.id) ids.add(row.id);
    fingerprints.add(createProjectGridFingerprint(row));
  };
  rows.forEach(add);
  return {
    add,
    has: (row: ProjectGridRow) =>
      (Boolean(row.id) && ids.has(row.id as string)) || fingerprints.has(createProjectGridFingerprint(row)),
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

export const getPastProjectDetailPath = (projectId: string) =>
  `/past-projects/project/${encodeURIComponent(projectId)}`;

export const getCurrentProjectDetailPath = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`;

const currentFrontendOrigin = () => {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.location.origin;
};

export const getPastProjectDetailUrl = (projectId: string) => {
  const path = getPastProjectDetailPath(projectId);
  const origin = currentFrontendOrigin();
  return origin ? new URL(path, origin).href : path;
};

/** The project page a row links to, or '' for rows without a project id (legacy snapshots). */
export const getProjectGridRowHref = (row: Pick<ProjectGridRow, 'id'>, scope: ProjectGridLinkScope) =>
  row.id ? (scope === 'past' ? getPastProjectDetailUrl(row.id) : getCurrentProjectDetailPath(row.id)) : '';

export const hasProjectGridDetails = (row: ProjectGridRow) => Boolean(row.id || row.abstract || row.student_names);

/**
 * Text as a search compares it: lowercase, without accents ("Živanović" matches "zivanovic"), with curly quotes made
 * straight and runs of spaces collapsed. Applied to both the query and the text searched.
 */
export const normalizeSearchText = (value: string) =>
  value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[\u2018\u2019\u201a\u201b\u2032]/g, "'")
    .replace(/[\u201c\u201d\u201e\u201f\u2033]/g, '"')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();

/**
 * The text a row is found by: what the page shows for it. That is the term, team code, team, title, organization,
 * industry, abstract and students in table order (so "2019 Spring CSE" matches across columns), then the term as
 * prose reads it ("Spring 2019 CSE"), the team code without its space and the class name the filter and project
 * page use. Hidden values (is_presenting's Yes/No) are left out, so "yes" or "no" do not match rows that never
 * show them.
 */
export const getProjectGridSearchValue = (row: ProjectGridRow, classLabels: Record<string, string> = {}) => {
  const teamCode = getProjectGridTeamCode(row);
  return normalizeSearchText(
    [
      row.semester_label,
      teamCode,
      row.team_name,
      row.project_title,
      row.organization,
      row.industry,
      row.abstract,
      row.student_names,
      formatTermForProse(row.semester_label),
      teamCode,
      teamCode.replace(/\s+/g, ''),
      classLabels[row.class_code] ?? '',
    ].join(' '),
  );
};

// One collator for every comparison: localeCompare with options builds a new collator on each call, which made
// sorting the 920-row archive take hundreds of milliseconds on a slower phone.
const textCollator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});

/** Case- and accent-insensitive text order, with numbers in numeric order ("CAP 9" before "CAP 10"). */
export const compareText = (left: string, right: string) => textCollator.compare(left, right);

/** Chronological (year, then season) when both labels parse, else as text. */
const compareSemesters = (left: string, right: string) => {
  const leftSemester = semesterSortKey(left);
  const rightSemester = semesterSortKey(right);
  if (!leftSemester || !rightSemester) return compareText(left, right);
  return (
    leftSemester.year - rightSemester.year ||
    leftSemester.seasonRank - rightSemester.seasonRank ||
    compareText(left, right)
  );
};

/** "Team number" order: class code, then team number within the class, as numbers ("CSE 2" before "CSE 10"). */
const compareTeams = (left: ProjectGridRow, right: ProjectGridRow) =>
  compareText(left.class_code || '', right.class_code || '') ||
  compareText(getDisplayTeamNumber(left), getDisplayTeamNumber(right));

export const sortProjectGridItems = (
  rows: ProjectGridItem[],
  sortField: ProjectGridColumnKey,
  sortDirection: ProjectGridSortDirection,
) => {
  const direction = sortDirection === 'asc' ? 1 : -1;
  const sorted = [...rows];
  sorted.sort((left, right) => {
    if (sortField === 'class_code') return direction * compareTeams(left, right);
    if (sortField === 'semester_label') {
      // Within a term the teams follow their team numbers, whichever way the terms run. The archive arrives
      // ordered by team number as text (1, 10, 11, ..., 2), which a stable sort would otherwise keep.
      return direction * compareSemesters(left.semester_label || '', right.semester_label || '') || compareTeams(left, right);
    }
    return direction * compareText(left[sortField] || '', right[sortField] || '');
  });
  return sorted;
};
