import type {ProjectGridRow, ProjectTableRow} from '../../features/projects/api';

export type {ProjectGridRow} from '../../features/projects/api';

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

export const CURRENT_PROJECT_GRID_COLUMNS: ProjectGridColumn[] = [
  ...PROJECT_GRID_COLUMNS,
  {key: 'is_presenting', label: 'Showcase Participation'},
];
export const PAST_PROJECT_GRID_COLUMNS = PROJECT_GRID_COLUMNS;

export const toProjectGridRow = (project: ProjectTableRow): ProjectGridRow => ({
  semester_label: project.semester_label,
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

export const createProjectGridFingerprint = (row: ProjectGridRow) =>
  JSON.stringify([
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
  ]);

export const createProjectGridItems = (rows: ProjectGridRow[], namespace: string): ProjectGridItem[] =>
  rows.map((row, index) => ({
    ...row,
    __key: `${namespace}-${index}-${createProjectGridFingerprint(row)}`,
  }));

export const stripProjectGridItem = (row: ProjectGridItem): ProjectGridRow => {
  const {__key, ...gridRow} = row;
  void __key;
  return gridRow;
};

export const hasProjectGridDetails = (row: ProjectGridRow) => Boolean(row.abstract || row.student_names);

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
    const comparison = leftValue.localeCompare(rightValue, undefined, {numeric: true, sensitivity: 'base'});
    return sortDirection === 'asc' ? comparison : -comparison;
  });
  return sorted;
};
