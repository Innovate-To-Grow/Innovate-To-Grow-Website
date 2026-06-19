import type {ProjectGridRow, ProjectTableRow} from '@/features/projects/api';
import {formatSemesterLabel} from '@/lib/semester';

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

export const PROJECT_GRID_COLUMNS: ProjectGridColumn[] = [
  {key: 'semester_label', label: 'Year-Semester'},
  {key: 'class_code', label: 'Class'},
  {key: 'team_number', label: 'Team#'},
  {key: 'team_name', label: 'Team Name'},
  {key: 'project_title', label: 'Project Title'},
  {key: 'organization', label: 'Organization'},
  {key: 'industry', label: 'Industry'},
];

export const PAST_PROJECT_GRID_COLUMNS = PROJECT_GRID_COLUMNS;

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

// `id` is deliberately excluded from the fingerprint (the row's dedup identity): an AI-search
// result carries a real id while an already-shared row may not, so including it would break dedup.
// id still rides on the row (via the spread) for the per-project Individual Link.
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

export const hasProjectGridDetails = (row: ProjectGridRow) => Boolean(row.id || row.abstract || row.student_names);

export const getProjectGridSearchValue = (row: ProjectGridRow) =>
  [
    row.semester_label,
    row.class_code,
    row.team_number,
    row.team_name,
    row.project_title,
    row.organization,
    row.industry,
    row.abstract,
    row.student_names,
    row.is_presenting,
  ]
    .join(' ')
    .toLowerCase();

export const sortProjectGridItems = (
  rows: ProjectGridItem[],
  sortField: ProjectGridColumnKey,
  sortDirection: ProjectGridSortDirection,
) => {
  const sorted = [...rows];
  sorted.sort((left, right) => {
    const leftValue = left[sortField] || '';
    const rightValue = right[sortField] || '';
    let comparison: number;

    if (sortField === 'semester_label') {
      const leftSemester = semesterSortKey(leftValue);
      const rightSemester = semesterSortKey(rightValue);
      if (leftSemester && rightSemester) {
        comparison =
          leftSemester.year - rightSemester.year ||
          leftSemester.seasonRank - rightSemester.seasonRank ||
          leftValue.localeCompare(rightValue, undefined, {numeric: true, sensitivity: 'base'});
      } else {
        comparison = leftValue.localeCompare(rightValue, undefined, {numeric: true, sensitivity: 'base'});
      }
    } else {
      comparison = leftValue.localeCompare(rightValue, undefined, {numeric: true, sensitivity: 'base'});
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });
  return sorted;
};
