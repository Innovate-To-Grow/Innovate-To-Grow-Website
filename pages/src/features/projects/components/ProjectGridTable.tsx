import './projects.css';
import {useId, type ReactNode} from 'react';
import {
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridLinkScope,
  type ProjectGridSortDirection,
} from './projectGrid';
import {ProjectGridDesktopTable} from './grid/ProjectGridDesktopTable';
import {ProjectGridMobileCards} from './grid/ProjectGridMobileCards';
import {ProjectGridPager} from './grid/ProjectGridPager';

export interface ProjectGridSortOption {
  field: ProjectGridColumnKey;
  label: string;
}

interface ProjectGridTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  filteredCount: number;
  totalCount: number;
  search: string;
  /** Replaces the search field (e.g. the AI search form). */
  searchControl?: ReactNode;
  controlsStatus?: ReactNode;
  searchPlaceholder?: string;
  /** Label above the search field. */
  searchLabel?: string;
  /** More fields for the filter well, after the search field (e.g. Class and Industry selects). */
  filterControls?: ReactNode;
  /** Shows a "Sort by" select in the results bar; Per page and View All Details move there too. */
  sortOptions?: ProjectGridSortOption[];
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  onSearchChange: (value: string) => void;
  onSortChange: (field: ProjectGridColumnKey) => void;
  /** Clears the extra filters too when the visitor clicks "Clear search" in the no-results state. */
  onClearFilters?: () => void;
  /** Extra hint and actions for the no-results state (e.g. a link to search past projects). */
  noResultsHint?: string;
  noResultsActions?: ReactNode;
  /**
   * Level of the no-results heading, one below the heading the table sits under: 2 under a page title,
   * 3 in a card titled with an h2, 4 in a card titled with an h3.
   */
  noResultsHeadingLevel?: 2 | 3 | 4;
  expandedKeys: Set<string>;
  onToggleExpanded: (rowKey: string) => void;
  onToggleAllDetails?: () => void;
  allDetailsExpanded?: boolean;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  pageSize: number;
  pageSizeOptions: number[];
  onPageSizeChange: (size: number) => void;
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  /** Plural noun for the result count ("projects", "teams"). */
  countLabel?: string;
  /** Actions shown above the results ('top', after the filter well) or under the table ('bottom'). */
  toolbar?: ReactNode;
  toolbarPlacement?: 'top' | 'bottom';
  /** Which project page a title links to. Past-project links open in a new tab so curation work is kept. */
  linkScope?: ProjectGridLinkScope;
  selectable?: boolean;
  selectedKeys?: Set<string>;
  selectAllStateRows?: ProjectGridItem[];
  onToggleSelected?: (rowKey: string) => void;
  onToggleSelectAll?: () => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  /** Show each row's Remove button disabled, e.g. while the rows are being turned into a shareable link. */
  deleteDisabled?: boolean;
  /** Retrieve missing details when archive rows are expanded; saved snapshots keep their own fields. */
  loadMissingDetails?: boolean;
  /** Marks rows already in the saved results with a tag after the project title. */
  isRowSaved?: (row: ProjectGridItem) => boolean;
  savedRowLabel?: string;
  /** Rows to emphasise, e.g. the ones the latest save just added. */
  highlightedKeys?: ReadonlySet<string>;
}

const singular = (noun: string) => (noun.endsWith('ies') ? `${noun.slice(0, -3)}y` : noun.replace(/s$/, ''));
const countNoun = (count: number, noun: string) => `${count} ${count === 1 ? singular(noun) : noun}`;

interface PageSizeFieldProps {
  value: number;
  options: number[];
  onChange: (size: number) => void;
}

const PageSizeField = ({value, options, onChange}: PageSizeFieldProps) => {
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

export const ProjectGridTable = ({
  columns,
  rows,
  pagedRows,
  filteredCount,
  totalCount,
  search,
  searchControl,
  controlsStatus,
  searchPlaceholder = 'Search projects...',
  searchLabel = 'Search',
  filterControls,
  sortOptions,
  sortField,
  sortDirection,
  onSearchChange,
  onSortChange,
  onClearFilters,
  noResultsHint,
  noResultsActions,
  noResultsHeadingLevel = 2,
  expandedKeys,
  onToggleExpanded,
  onToggleAllDetails,
  allDetailsExpanded = false,
  page,
  totalPages,
  onPageChange,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  loading,
  error,
  emptyMessage = 'No projects found.',
  countLabel = 'projects',
  toolbar,
  toolbarPlacement = 'top',
  linkScope = 'current',
  selectable = false,
  selectedKeys = new Set<string>(),
  selectAllStateRows,
  onToggleSelected,
  onToggleSelectAll,
  onDeleteRow,
  deleteDisabled = false,
  loadMissingDetails = false,
  isRowSaved,
  savedRowLabel,
  highlightedKeys,
}: ProjectGridTableProps) => {
  const searchInputId = useId();
  const sortSelectId = useId();
  const query = search.trim();
  const toolbarElement = toolbar ? (
    <div className={`project-grid-toolbar${toolbarPlacement === 'bottom' ? ' project-grid-toolbar--bottom' : ''}`}>
      {toolbar}
    </div>
  ) : null;

  const pageSizeField = <PageSizeField value={pageSize} options={pageSizeOptions} onChange={onPageSizeChange} />;
  const toggleDetailsButton = onToggleAllDetails ? (
    <button
      type="button"
      className={`itg-btn ${sortOptions ? 'itg-btn-text' : 'itg-btn-outline'} project-grid-toggle-details`}
      onClick={onToggleAllDetails}
    >
      {allDetailsExpanded ? 'Hide All Details' : 'View All Details'}
    </button>
  ) : null;

  // The Sort select lists the offered fields; a column sorted from its header joins them so the select never
  // shows a field the table is not sorted by.
  const sortChoices =
    sortOptions && !sortOptions.some((option) => option.field === sortField)
      ? [
          ...sortOptions,
          {field: sortField, label: columns.find((column) => column.key === sortField)?.label ?? String(sortField)},
        ]
      : sortOptions;

  const isNarrowed = filteredCount !== totalCount;
  const firstShown = page * pageSize + 1;
  const lastShown = Math.min((page + 1) * pageSize, filteredCount);
  const showing = filteredCount > 0 ? ` · showing ${firstShown}–${lastShown}` : '';
  const matchText = `${filteredCount === 1 ? 'matches' : 'match'} ${query ? `“${query}”` : 'the filters'}`;
  const noResults = totalCount > 0 && filteredCount === 0;
  const NoResultsHeading = `h${noResultsHeadingLevel}` as const;

  return (
    <div className="project-grid-table-shell">
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
          {sortOptions ? null : pageSizeField}
          {sortOptions ? null : toggleDetailsButton}
        </div>
        {controlsStatus ? <div className="project-grid-controls-status">{controlsStatus}</div> : null}
      </div>

      {toolbarPlacement === 'top' ? toolbarElement : null}

      {loading ? <p className="project-grid-state">Loading project data...</p> : null}
      {error ? (
        <p className="project-grid-state project-grid-state-error itg-error" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && !error ? (
        <>
          {totalCount > 0 ? (
            <div className="project-grid-results-bar">
              <p className="project-grid-count" aria-live="polite">
                {isNarrowed ? (
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
                  {pageSizeField}
                  {toggleDetailsButton}
                </div>
              ) : null}
            </div>
          ) : null}

          {totalCount === 0 ? <p className="project-grid-empty">{emptyMessage}</p> : null}

          {noResults ? (
            <div className="itg-empty-state project-grid-no-results">
              <NoResultsHeading className="itg-empty-state-title">
                No {countLabel} {query ? `match “${query}”` : 'match the filters'}
              </NoResultsHeading>
              <p className="itg-empty-state-text">
                Check the spelling, or try a team, sponsor or industry name.
                {noResultsHint ? ` ${noResultsHint}` : ''}
              </p>
              <div className="itg-empty-state-actions">
                <button
                  type="button"
                  className="itg-btn itg-btn-outline"
                  onClick={() => {
                    onSearchChange('');
                    onClearFilters?.();
                  }}
                >
                  Clear search
                </button>
                {noResultsActions}
              </div>
            </div>
          ) : null}

          {totalCount > 0 && !noResults ? (
            <>
              <ProjectGridDesktopTable
                columns={columns}
                rows={rows}
                pagedRows={pagedRows}
                linkScope={linkScope}
                selectable={selectable}
                selectedKeys={selectedKeys}
                selectAllStateRows={selectAllStateRows}
                onToggleSelected={onToggleSelected}
                onToggleSelectAll={onToggleSelectAll}
                sortField={sortField}
                sortDirection={sortDirection}
                onSortChange={onSortChange}
                expandedKeys={expandedKeys}
                onToggleExpanded={onToggleExpanded}
                onDeleteRow={onDeleteRow}
                deleteDisabled={deleteDisabled}
                loadMissingDetails={loadMissingDetails}
                isRowSaved={isRowSaved}
                savedRowLabel={savedRowLabel}
                highlightedKeys={highlightedKeys}
              />

              <ProjectGridMobileCards
                columns={columns}
                pagedRows={pagedRows}
                linkScope={linkScope}
                expandedKeys={expandedKeys}
                onToggleExpanded={onToggleExpanded}
                selectable={selectable}
                selectedKeys={selectedKeys}
                onToggleSelected={onToggleSelected}
                onDeleteRow={onDeleteRow}
                deleteDisabled={deleteDisabled}
                loadMissingDetails={loadMissingDetails}
                isRowSaved={isRowSaved}
                savedRowLabel={savedRowLabel}
                highlightedKeys={highlightedKeys}
              />
            </>
          ) : null}

          {totalPages > 1 ? <ProjectGridPager page={page} totalPages={totalPages} onPageChange={onPageChange} /> : null}
        </>
      ) : null}

      {toolbarPlacement === 'bottom' ? toolbarElement : null}
    </div>
  );
};
