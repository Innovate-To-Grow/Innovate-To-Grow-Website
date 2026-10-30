import {useId, type ReactNode, type Ref} from 'react';
import type {ProjectGridColumnKey, ProjectGridSortDirection} from '../contracts/projectGrid';
import type {ProjectGridSortOption, ProjectGridTableProps} from '../contracts/gridTableProps';

// Every changing piece of text below is the only child of its element. Browser page translation (Chrome's
// Translate) swaps text nodes for its own <font> elements; React then updated or removed text nodes that were no
// longer in the page, which left counts stale or threw "removeChild" and took the whole page down. A single string
// child is written through textContent, which replaces whatever the translator put there.

const singular = (noun: string) => (noun.endsWith('ies') ? `${noun.slice(0, -3)}y` : noun.replace(/s$/, ''));
const countNoun = (count: number, noun: string) => `${count} ${count === 1 ? singular(noun) : noun}`;

/** Under the count when the server would not search the abstracts: the matches shown come from the rows' own text. */
const ABSTRACTS_SKIPPED = 'Abstracts were not searched: this search term is too common. Try a longer one.';

/** "Engineering Capstone (CAP)" or "Engineering Capstone (CAP) and AeroSpace". */
const joinFilters = (filters: string[]) => filters.join(' and ');

type ResultsBarProps = Pick<
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
  /** The server declined to search the abstracts for this search (ProjectGridServerSearch.tooBroad). */
  abstractsSkipped?: boolean;
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

const sortValue = (field: ProjectGridColumnKey, direction: ProjectGridSortDirection) => `${field}:${direction}`;

// The Sort select lists the offered fields, each in both directions (on phones there are no column headers to
// reverse a sort with); a column sorted from its header joins them so the select never shows a sort the table
// is not in.
const sortChoicesFor = (
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

/** The count line: the bold count, then the rest of the sentence. */
const countText = ({
  filteredCount,
  totalCount,
  page,
  pageSize,
  query,
  countLabel,
  activeFilters,
}: Pick<ResultsBarProps, 'filteredCount' | 'totalCount' | 'page' | 'pageSize' | 'query' | 'countLabel' | 'activeFilters'>) => {
  const showing =
    filteredCount > 0 ? ` · showing ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, filteredCount)}` : '';
  if (filteredCount === totalCount) return {bold: countNoun(totalCount, countLabel), rest: showing};
  const verb = filteredCount === 1 ? 'matches' : 'match';
  const filters = activeFilters.length ? `in ${joinFilters(activeFilters)}` : '';
  // "match “a” in AeroSpace", "in AeroSpace", or "match “a”" (and "match the filters" when the caller names none).
  const criteria = query ? [`${verb} “${query}”`, filters].filter(Boolean).join(' ') : filters || `${verb} the filters`;
  return {bold: `${filteredCount} of ${totalCount}`, rest: ` ${countLabel} ${criteria}${showing}`};
};

/**
 * "N projects · showing a–b" (or "N of M match …"), and the sort select when the table offers one. With no rows
 * matching, only the count stays: the no-results message and its Clear button come next, not controls for rows.
 */
export const ProjectGridResultsBar = ({
  columns,
  sortOptions,
  sortField,
  sortDirection,
  onSortChange,
  onSortSelect,
  abstractsSkipped = false,
  pageControls,
  countRef,
  ...counts
}: ResultsBarProps) => {
  const sortSelectId = useId();
  const sortChoices = sortChoicesFor(sortOptions, sortField, columns);
  const {bold, rest} = countText(counts);

  const selectSort = (value: string) => {
    const [field, direction] = value.split(':') as [ProjectGridColumnKey, ProjectGridSortDirection];
    if (onSortSelect) onSortSelect(field, direction);
    else onSortChange(field);
  };

  return (
    <div className="project-grid-results-bar">
      <p ref={countRef} className="project-grid-count" aria-live="polite" tabIndex={-1}>
        <strong>{bold}</strong>
        <span>{rest}</span>
        {/* In the count line, so it is read out with the count; on a line of its own. */}
        {abstractsSkipped ? <span className="project-grid-count-note">{ABSTRACTS_SKIPPED}</span> : null}
      </p>
      {sortChoices && counts.filteredCount > 0 ? (
        <div className="project-grid-results-controls">
          <div className="project-grid-sort">
            <label htmlFor={sortSelectId}>Sort by</label>
            <select
              id={sortSelectId}
              className="itg-select project-grid-select"
              value={sortValue(sortField, sortDirection)}
              onChange={(event) => selectSort(event.target.value)}
            >
              {sortChoices.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          {pageControls}
        </div>
      ) : null}
    </div>
  );
};

type NoResultsProps = Pick<ProjectGridTableProps, 'noResultsHint' | 'noResultsActions'> & {
  query: string;
  countLabel: string;
  activeFilters: string[];
  headingLevel: 2 | 3 | 4;
  /** The server is still searching the abstracts, which may still find rows. */
  searching?: boolean;
  onClear: () => void;
};

/** The heading, hint and clear button, naming the filters when they (not only the search) hide every row. */
const noResultsText = ({
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
  const clearLabel = filters ? (query ? 'Clear search and filters' : 'Clear filters') : 'Clear search';
  return {heading, hint: noResultsHint ? `${advice} ${noResultsHint}` : advice, clearLabel};
};

export const ProjectGridNoResults = ({headingLevel, noResultsActions, searching, onClear, ...text}: NoResultsProps) => {
  const NoResultsHeading = `h${headingLevel}` as const;
  const {heading, hint, clearLabel} = noResultsText(text);
  return (
    <div className="itg-empty-state project-grid-no-results">
      <NoResultsHeading className="itg-empty-state-title">{heading}</NoResultsHeading>
      <p className="itg-empty-state-text">{hint}</p>
      {/* The count line above is the live region: it reads out the matches the server adds. */}
      {searching ? <p className="itg-empty-state-text project-grid-searching">Still searching project abstracts…</p> : null}
      <div className="itg-empty-state-actions">
        <button type="button" className="itg-btn itg-btn-outline" onClick={onClear}>
          {clearLabel}
        </button>
        {noResultsActions}
      </div>
    </div>
  );
};
