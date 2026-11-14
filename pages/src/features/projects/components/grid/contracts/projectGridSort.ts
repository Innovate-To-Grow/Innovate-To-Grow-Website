import type {ProjectGridRow} from '@/features/projects/api';
import {
    formatTermForProse,
    getDisplayTeamNumber,
    getProjectGridTeamCode,
    type ProjectGridColumnKey,
    type ProjectGridItem,
    type ProjectGridSortDirection,
} from './projectGridModel';

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

/** The order rows that tie on the sorted column keep, whichever way it runs: by term, then by team number. */
const compareTies = (left: ProjectGridRow, right: ProjectGridRow) =>
  compareSemesters(left.semester_label || '', right.semester_label || '') || compareTeams(left, right);

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
    // Ties do not keep the API's order (which lists presenting teams first): they follow the team numbers.
    return direction * compareText(left[sortField] || '', right[sortField] || '') || compareTies(left, right);
  });
  return sorted;
};
