import {useId, type ReactNode} from 'react';
import type {ProjectGridColumnKey} from '../projectGrid';
import type {ProjectGridSortOption, ProjectGridTableProps} from './gridTableProps';

const singular = (noun: string) => (noun.endsWith('ies') ? `${noun.slice(0, -3)}y` : noun.replace(/s$/, ''));
const countNoun = (count: number, noun: string) => `${count} ${count === 1 ? singular(noun) : noun}`;

type ResultsBarProps = Pick<
  ProjectGridTableProps,
  'columns' | 'filteredCount' | 'totalCount' | 'page' | 'pageSize' | 'sortOptions' | 'sortField' | 'onSortChange'
> & {
  query: string;
  countLabel: string;
  /** Per page and View All Details, shown beside the sort select. */
  pageControls: ReactNode;
};

// The Sort select lists the offered fields; a column sorted from its header joins them so the select never
// shows a field the table is not sorted by.
const sortChoicesFor = (
  sortOptions: ProjectGridSortOption[] | undefined,
  sortField: ProjectGridColumnKey,
  columns: ProjectGridTableProps['columns'],
) =>
  sortOptions && !sortOptions.some((option) => option.field === sortField)
    ? [...sortOptions, {field: sortField, label: columns.find((column) => column.key === sortField)?.label ?? String(sortField)}]
    : sortOptions;

/** "N projects · showing a–b" (or "N of M match …"), and the sort select when the table offers one. */
export const ProjectGridResultsBar = ({
  columns,
  filteredCount,
  totalCount,
  page,
  pageSize,
  sortOptions,
  sortField,
  onSortChange,
  query,
  countLabel,
  pageControls,
}: ResultsBarProps) => {
  const sortSelectId = useId();
  const sortChoices = sortChoicesFor(sortOptions, sortField, columns);
  const firstShown = page * pageSize + 1;
  const lastShown = Math.min((page + 1) * pageSize, filteredCount);
  const showing = filteredCount > 0 ? ` · showing ${firstShown}–${lastShown}` : '';
  const matchText = `${filteredCount === 1 ? 'matches' : 'match'} ${query ? `“${query}”` : 'the filters'}`;

  return (
    <div className="project-grid-results-bar">
      <p className="project-grid-count" aria-live="polite">
        {filteredCount !== totalCount ? (
          <>
            <strong>
              {filteredCount} of {totalCount}
            </strong>{' '}
            {countLabel} {matchText}
            {showing}
          </>
        ) : (
          <>
            <strong>{countNoun(totalCount, countLabel)}</strong>
            {showing}
          </>
        )}
      </p>
      {sortChoices ? (
        <div className="project-grid-results-controls">
          <div className="project-grid-sort">
            <label htmlFor={sortSelectId}>Sort by</label>
            <select
              id={sortSelectId}
              className="itg-select project-grid-select"
              value={sortField}
              onChange={(event) => onSortChange(event.target.value as ProjectGridColumnKey)}
            >
              {sortChoices.map((option) => (
                <option key={option.field} value={option.field}>
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
  headingLevel: 2 | 3 | 4;
  onClear: () => void;
};

export const ProjectGridNoResults = ({query, countLabel, headingLevel, noResultsHint, noResultsActions, onClear}: NoResultsProps) => {
  const NoResultsHeading = `h${headingLevel}` as const;
  return (
    <div className="itg-empty-state project-grid-no-results">
      <NoResultsHeading className="itg-empty-state-title">
        No {countLabel} {query ? `match “${query}”` : 'match the filters'}
      </NoResultsHeading>
      <p className="itg-empty-state-text">
        Check the spelling, or try a team, sponsor or industry name.
        {noResultsHint ? ` ${noResultsHint}` : ''}
      </p>
      <div className="itg-empty-state-actions">
        <button type="button" className="itg-btn itg-btn-outline" onClick={onClear}>
          Clear search
        </button>
        {noResultsActions}
      </div>
    </div>
  );
};
