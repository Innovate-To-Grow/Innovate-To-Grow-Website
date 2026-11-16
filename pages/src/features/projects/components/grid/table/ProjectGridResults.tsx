import {useId, type RefObject} from 'react';
import type {ProjectGridColumnKey, ProjectGridSortDirection} from '../contracts/projectGrid';
import type {ProjectGridTableProps} from '../contracts/gridTableProps';
import {
  ABSTRACTS_SKIPPED,
  countText,
  type NoResultsProps,
  noResultsText,
  type ResultsBarProps,
  sortChoicesFor,
  sortValue,
} from './projectGridResultsText';

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
  abstractsSkipped = null,
  pageControls,
  countRef,
  ...counts
}: ResultsBarProps) => {
  const sortSelectId = useId();
  const sortChoices = sortChoicesFor(sortOptions, sortField, columns);
  const {bold, rest, range} = countText(counts);

  const selectSort = (value: string) => {
    const [field, direction] = value.split(':') as [ProjectGridColumnKey, ProjectGridSortDirection];
    if (onSortSelect) onSortSelect(field, direction);
    else onSortChange(field);
  };

  return (
    <div className="project-grid-results-bar">
      <p ref={countRef} className="project-grid-count" aria-live="polite" tabIndex={-1}>
        <strong>{bold}</strong>
        <span>{`${rest}${range ? ' ' : ''}`}</span>
        {range ? <span className="project-grid-count-range">{range}</span> : null}
        {/* In the count line, so it is read out with the count; on a line of its own. */}
        {abstractsSkipped ? <span className="project-grid-count-note">{ABSTRACTS_SKIPPED[abstractsSkipped]}</span> : null}
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

type EmptyProps = Pick<ProjectGridTableProps, 'emptyTitle' | 'emptyActions'> & {
  emptyMessage: string;
  headingLevel: 2 | 3 | 4;
  /** The heading (or the message), which takes focus after Try Again when no rows came back (useRetryFocus). */
  emptyRef: RefObject<HTMLElement | null>;
};

/**
 * No rows at all. With a title (an empty schedule), a heading, the text and the caller's action, laid out like the
 * no-results state; without one, the message alone (an empty table in the builder).
 */
export const ProjectGridEmpty = ({emptyTitle, emptyMessage, emptyActions, headingLevel, emptyRef}: EmptyProps) => {
  // A heading or a paragraph: either one is the element focus goes to.
  const setEmptyElement = (element: HTMLElement | null) => {
    emptyRef.current = element;
  };
  if (!emptyTitle) {
    return (
      <p ref={setEmptyElement} className="project-grid-empty" tabIndex={-1}>
        {emptyMessage}
      </p>
    );
  }
  const EmptyHeading = `h${headingLevel}` as const;
  return (
    <div className="itg-empty-state project-grid-empty-state">
      <EmptyHeading ref={setEmptyElement} className="itg-empty-state-title" tabIndex={-1}>
        {emptyTitle}
      </EmptyHeading>
      <p className="itg-empty-state-text">{emptyMessage}</p>
      {emptyActions ? <div className="itg-empty-state-actions">{emptyActions}</div> : null}
    </div>
  );
};
