import {type ReactNode, type Ref} from 'react';
import type {ProjectGridColumnKey, ProjectGridSortDirection} from '../contracts/projectGrid';
import type {ProjectGridSortOption, ProjectGridTableProps} from '../contracts/gridTableProps';

// Every changing piece of text below is the only child of its element. Browser page translation (Chrome's
// Translate) swaps text nodes for its own <font> elements; React then updated or removed text nodes that were no
// longer in the page, which left counts stale or threw "removeChild" and took the whole page down. A single string
// child is written through textContent, which replaces whatever the translator put there.

const singular = (noun: string) => (noun.endsWith('ies') ? `${noun.slice(0, -3)}y` : noun.replace(/s$/, ''));
const countNoun = (count: number, noun: string) => `${count} ${count === 1 ? singular(noun) : noun}`;

/** Why the server did not search the abstracts (see ProjectGridServerSearch): the term was too common, or it failed. */
export type AbstractsSkipped = 'too-broad' | 'failed';

/** Under the count when the abstracts were not searched: the matches shown come from the rows' own text. */
export const ABSTRACTS_SKIPPED: Record<AbstractsSkipped, string> = {
  'too-broad': 'Abstracts were not searched: this search term is too common. Try a longer one.',
  // A new search asks again; the same one keeps this answer.
  failed: 'Abstracts were not searched: something went wrong. Change the search to try again.',
};

/** "Engineering Capstone (CAP)" or "Engineering Capstone (CAP) and AeroSpace". */
const joinFilters = (filters: string[]) => filters.join(' and ');

export type ResultsBarProps = Pick<
  ProjectGridTableProps,
  | 'columns'
  | 'filteredCount'
  | 'totalCount'
  | 'page'
  | 'pageSize'
  | 'sortOptions'
  | 'sortField'
  | 'sortDirection'
  | 'onSortChange'
  | 'onSortSelect'
> & {
  query: string;
  countLabel: string;
  /** The extra filters in use (see ProjectGridTableProps.activeFilters). */
  activeFilters: string[];
  /** Why the abstracts were not searched for this search, if they were not (ProjectGridServerSearch). */
  abstractsSkipped?: AbstractsSkipped | null;
  /** Per page and View All Details, shown beside the sort select while there are rows to act on. */
  pageControls: ReactNode;
  /** The count line, which takes focus after a page change. */
  countRef?: Ref<HTMLParagraphElement>;
};

/** How a direction reads for a field: "low to high" for team numbers, "oldest first" for terms, else "A to Z". */
const directionLabel = (field: ProjectGridColumnKey, direction: ProjectGridSortDirection) => {
  if (field === 'class_code') return direction === 'asc' ? 'low to high' : 'high to low';
  if (field === 'semester_label') return direction === 'asc' ? 'oldest first' : 'newest first';
  return direction === 'asc' ? 'A to Z' : 'Z to A';
};

export const sortValue = (field: ProjectGridColumnKey, direction: ProjectGridSortDirection) => `${field}:${direction}`;

// The Sort select lists the offered fields, each in both directions (on phones there are no column headers to
// reverse a sort with); a column sorted from its header joins them so the select never shows a sort the table
// is not in.
export const sortChoicesFor = (
  sortOptions: ProjectGridSortOption[] | undefined,
  sortField: ProjectGridColumnKey,
  columns: ProjectGridTableProps['columns'],
) => {
  if (!sortOptions) return undefined;
  const fields = sortOptions.some((option) => option.field === sortField)
    ? sortOptions
    : [...sortOptions, {field: sortField, label: columns.find((column) => column.key === sortField)?.label ?? String(sortField)}];
  return fields.flatMap(({field, label}) =>
    (['asc', 'desc'] as const).map((direction) => ({
      value: sortValue(field, direction),
      label: `${label} (${directionLabel(field, direction)})`,
    })),
  );
};

/**
 * The count line: the bold count, the rest of the sentence, and the range shown ("· showing 1–10", or '' with no
 * rows), which is kept apart so it never breaks over two lines.
 */
export const countText = ({
  filteredCount,
  totalCount,
  page,
  pageSize,
  query,
  countLabel,
  activeFilters,
}: Pick<ResultsBarProps, 'filteredCount' | 'totalCount' | 'page' | 'pageSize' | 'query' | 'countLabel' | 'activeFilters'>) => {
  const range =
    filteredCount > 0 ? `· showing ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, filteredCount)}` : '';
  if (filteredCount === totalCount) return {bold: countNoun(totalCount, countLabel), rest: '', range};
  const verb = filteredCount === 1 ? 'matches' : 'match';
  const filters = activeFilters.length ? `in ${joinFilters(activeFilters)}` : '';
  // "match “a” in AeroSpace", "in AeroSpace", or "match “a”" (and "match the filters" when the caller names none).
  const criteria = query ? [`${verb} “${query}”`, filters].filter(Boolean).join(' ') : filters || `${verb} the filters`;
  return {bold: `${filteredCount} of ${totalCount}`, rest: ` ${countLabel} ${criteria}`, range};
};

export type NoResultsProps = Pick<ProjectGridTableProps, 'noResultsHint' | 'noResultsActions'> & {
  query: string;
  countLabel: string;
  activeFilters: string[];
  headingLevel: 2 | 3 | 4;
  /** The server is still searching the abstracts, which may still find rows. */
  searching?: boolean;
  onClear: () => void;
};

/** The heading, hint and clear button, naming the filters when they (not only the search) hide every row. */
export const noResultsText = ({
  query,
  countLabel,
  activeFilters,
  noResultsHint,
}: Omit<NoResultsProps, 'headingLevel' | 'searching' | 'onClear'>) => {
  const filters = activeFilters.length ? `in ${joinFilters(activeFilters)}` : '';
  const heading = query
    ? [`No ${countLabel} match “${query}”`, filters].filter(Boolean).join(' ')
    : `No ${countLabel} ${filters || 'match the filters'}`;
  let advice = 'Check the spelling, or try a project title, team, organization, industry or student name.';
  if (filters) {
    advice = query ? `Clear the filters to search all ${countLabel}, or check the spelling.` : `Clear the filters to see all ${countLabel}.`;
  }
  const clearLabel = filters ? (query ? 'Clear Search and Filters' : 'Clear Filters') : 'Clear Search';
  return {heading, hint: noResultsHint ? `${advice} ${noResultsHint}` : advice, clearLabel};
};
