import {useId, type ReactNode} from 'react';
import type {ProjectGridTableProps} from './gridTableProps';

interface PageSizeFieldProps {
  value: number;
  options: number[];
  onChange: (size: number) => void;
}

export const PageSizeField = ({value, options, onChange}: PageSizeFieldProps) => {
  const selectId = useId();
  return (
    <div className="itg-field project-grid-page-size">
      <label className="project-grid-field-label" htmlFor={selectId}>
        Per page
      </label>
      <select
        id={selectId}
        className="itg-select project-grid-select"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
};

type ControlsProps = Pick<
  ProjectGridTableProps,
  | 'search'
  | 'searchControl'
  | 'controlsStatus'
  | 'searchPlaceholder'
  | 'searchLabel'
  | 'filterControls'
  | 'onSearchChange'
> & {
  /** Per page and View All Details, when the results bar does not hold them (no sort select). */
  pageControls: ReactNode;
};

/** The filter well: the search field (or a replacement such as the AI search form) and any extra filters. */
export const ProjectGridControls = ({
  search,
  searchControl,
  controlsStatus,
  searchPlaceholder,
  searchLabel,
  filterControls,
  onSearchChange,
  pageControls,
}: ControlsProps) => {
  const searchInputId = useId();
  return (
    <div className="project-grid-controls itg-well">
      <div className={`project-grid-controls-row${filterControls ? ' has-filters' : ''}`}>
        {searchControl ?? (
          <div className="itg-field project-grid-search-field">
            <label className="project-grid-field-label" htmlFor={searchInputId}>
              {searchLabel}
            </label>
            <input
              id={searchInputId}
              type="search"
              className="itg-input project-grid-search-input"
              value={search}
              placeholder={searchPlaceholder}
              onChange={(event) => onSearchChange(event.target.value)}
            />
          </div>
        )}
        {filterControls}
        {pageControls}
      </div>
      {controlsStatus ? <div className="project-grid-controls-status">{controlsStatus}</div> : null}
    </div>
  );
};
