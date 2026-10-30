import '../../styles/cascade/projects.css';
import {useEffect, useRef, type RefObject} from 'react';
import {useMediaQuery} from '@/features/layout';
import {ProjectGridControls, PageSizeField} from '../controls/ProjectGridControls';
import {ProjectGridDesktopTable} from './ProjectGridDesktopTable';
import {ProjectGridMobileCards} from './ProjectGridMobileCards';
import {ProjectGridPager} from '../controls/ProjectGridPager';
import {ProjectGridNoResults, ProjectGridResultsBar} from './ProjectGridResults';
import {useDetailsAnnouncements} from '../state/useDetailsAnnouncements';
import {useRetryFocus} from '../state/useRetryFocus';
import type {ProjectGridTableProps} from '../contracts/gridTableProps';

export type {ProjectGridSortOption} from '../contracts/gridTableProps';

/** Where the table gives way to the phone list; the phone styles in projectsResponsive.css start at the same width. */
const PHONE_LAYOUT_QUERY = '(max-width: 768px)';

const NO_ACTIVE_FILTERS: string[] = [];

/**
 * After the pager changes page: focus the count line at the top of the results (the pressed step button may have
 * just been disabled, which dropped focus to the page) and, when it is out of view, scroll it under the sticky
 * header (the page's scroll-padding-top), so the new page is read from its first row, not its last.
 */
const showResultsStart = (countLine: HTMLElement) => {
  countLine.focus({preventScroll: true});
  const headerSpace = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
  const {top} = countLine.getBoundingClientRect();
  if (top < headerSpace || top > window.innerHeight) countLine.scrollIntoView({block: 'start'});
};

function withGridDefaults({
  searchPlaceholder = 'Search projects...',
  searchLabel = 'Search',
  noResultsHeadingLevel = 2,
  allDetailsExpanded = false,
  emptyMessage = 'No projects found.',
  countLabel = 'projects',
  toolbarPlacement = 'top',
  linkScope = 'current',
  activeFilters = NO_ACTIVE_FILTERS,
  selectable = false,
  selectedKeys = new Set<string>(),
  deleteDisabled = false,
  loadMissingDetails = false,
  ...props
}: ProjectGridTableProps) {
  return {
    ...props,
    searchPlaceholder,
    searchLabel,
    noResultsHeadingLevel,
    allDetailsExpanded,
    emptyMessage,
    countLabel,
    toolbarPlacement,
    linkScope,
    activeFilters,
    selectable,
    selectedKeys,
    deleteDisabled,
    loadMissingDetails,
  };
}

type ResolvedGridProps = ReturnType<typeof withGridDefaults>;

type DetailsAnnouncements = ReturnType<typeof useDetailsAnnouncements>;

interface PageControlsProps {
  grid: ResolvedGridProps;
  /** Opens or closes every row's details and says so (useDetailsAnnouncements). */
  onToggleAllDetails: () => void;
}

/**
 * Per page and View All Details: in the filter well, or beside the sort select when there is one. The toggle is
 * the same outlined button in both places.
 */
const PageControls = ({grid, onToggleAllDetails}: PageControlsProps) => (
  <>
    <PageSizeField value={grid.pageSize} options={grid.pageSizeOptions} onChange={grid.onPageSizeChange} />
    {grid.onToggleAllDetails ? (
      <button
        type="button"
        className="itg-btn itg-btn-outline project-grid-toggle-details"
        onClick={onToggleAllDetails}
        // With no rows shown it would only change its own label.
        disabled={grid.filteredCount === 0}
      >
        {grid.allDetailsExpanded ? 'Hide All Details' : 'View All Details'}
      </button>
    ) : null}
  </>
);

interface ResultsProps {
  grid: ResolvedGridProps;
  details: DetailsAnnouncements;
  /** The filter well's search field, focused when "Clear search" removes itself. */
  searchInputRef: RefObject<HTMLInputElement | null>;
  /** The count line: focus goes there after a page change, and after Try again (see useRetryFocus). */
  countRef: RefObject<HTMLParagraphElement | null>;
  /** The empty message, which takes focus after Try again when no rows came back. */
  emptyRef: RefObject<HTMLParagraphElement | null>;
}

/** Everything below the filter well once the rows are loaded: counts, empty states, the rows and the pager. */
const ProjectGridResults = ({grid, details, searchInputRef, countRef, emptyRef}: ResultsProps) => {
  // Only the layout the screen shows is rendered: mounting both and hiding one with CSS doubled the rows (and their
  // opened details) that every sort, page change and "View All Details" had to render.
  const isPhone = useMediaQuery(PHONE_LAYOUT_QUERY);
  const pagerTarget = useRef<number | null>(null);
  const query = grid.search.trim();
  const noResults = grid.totalCount > 0 && grid.filteredCount === 0;
  const rowProps = {
    columns: grid.columns,
    pagedRows: grid.pagedRows,
    linkScope: grid.linkScope,
    selectable: grid.selectable,
    selectedKeys: grid.selectedKeys,
    onToggleSelected: grid.onToggleSelected,
    expandedKeys: grid.expandedKeys,
    onToggleExpanded: details.toggleRow,
    onDeleteRow: grid.onDeleteRow,
    deleteDisabled: grid.deleteDisabled,
    loadMissingDetails: grid.loadMissingDetails,
    isRowSaved: grid.isRowSaved,
    savedRowLabel: grid.savedRowLabel,
    highlightedKeys: grid.highlightedKeys,
    announceDetails: details.announceRows,
  };

  // Only a page the pager asked for moves focus and scroll; a search or sort that starts over at page 1 does not.
  useEffect(() => {
    const requested = pagerTarget.current;
    pagerTarget.current = null;
    if (requested === grid.page && countRef.current) showResultsStart(countRef.current);
  }, [countRef, grid.page]);
  const changePage = (page: number) => {
    pagerTarget.current = page;
    grid.onPageChange(page);
  };

  return (
    <>
      {grid.totalCount > 0 ? (
        <ProjectGridResultsBar
          columns={grid.columns}
          filteredCount={grid.filteredCount}
          totalCount={grid.totalCount}
          page={grid.page}
          pageSize={grid.pageSize}
          sortOptions={grid.sortOptions}
          sortField={grid.sortField}
          sortDirection={grid.sortDirection}
          onSortChange={grid.onSortChange}
          onSortSelect={grid.onSortSelect}
          query={query}
          countLabel={grid.countLabel}
          activeFilters={grid.activeFilters}
          pageControls={<PageControls grid={grid} onToggleAllDetails={details.toggleAllDetails} />}
          countRef={countRef}
        />
      ) : null}

      {grid.totalCount === 0 ? (
        <p ref={emptyRef} className="project-grid-empty" tabIndex={-1}>
          {grid.emptyMessage}
        </p>
      ) : null}

      {noResults ? (
        <ProjectGridNoResults
          query={query}
          countLabel={grid.countLabel}
          activeFilters={grid.activeFilters}
          headingLevel={grid.noResultsHeadingLevel}
          searching={grid.searchPending}
          noResultsHint={grid.noResultsHint}
          noResultsActions={grid.noResultsActions}
          onClear={() => {
            // The button leaves with the empty state: move focus first, to the search field (or, when the well
            // holds another search control, the count line), so it does not fall to the page.
            (searchInputRef.current ?? countRef.current)?.focus();
            grid.onSearchChange('');
            grid.onClearFilters?.();
          }}
        />
      ) : null}

      {grid.totalCount > 0 && !noResults ? (
        isPhone ? (
          <ProjectGridMobileCards {...rowProps} />
        ) : (
          <ProjectGridDesktopTable
            {...rowProps}
            tableLabel={grid.tableLabel}
            rows={grid.rows}
            selectAllStateRows={grid.selectAllStateRows}
            onToggleSelectAll={grid.onToggleSelectAll}
            sortField={grid.sortField}
            sortDirection={grid.sortDirection}
            onSortChange={grid.onSortChange}
          />
        )
      ) : null}

      {grid.totalPages > 1 ? (
        <ProjectGridPager
          page={grid.page}
          totalPages={grid.totalPages}
          onPageChange={changePage}
          label={grid.tableLabel ? `${grid.tableLabel} pages` : undefined}
        />
      ) : null}
    </>
  );
};

/**
 * The projects grid: a filter well, an optional toolbar, the results (a table on wide screens, a list on
 * phones) and the pager. Paging, sorting and selection state come from `useProjectGridTable`.
 */
export const ProjectGridTable = (props: ProjectGridTableProps) => {
  const grid = withGridDefaults(props);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const details = useDetailsAnnouncements(grid);
  const countRef = useRef<HTMLParagraphElement>(null);
  const emptyRef = useRef<HTMLParagraphElement>(null);
  const {loadingRef, retryRef, retry} = useRetryFocus(Boolean(grid.loading), grid.error, countRef, emptyRef);
  const {onRetry} = grid;
  const toolbarElement = grid.toolbar ? (
    <div className={`project-grid-toolbar${grid.toolbarPlacement === 'bottom' ? ' project-grid-toolbar--bottom' : ''}`}>
      {grid.toolbar}
    </div>
  ) : null;

  return (
    <div className="project-grid-table-shell">
      {/* Always in the page, so each new message is read out (a polite live region, like the count line). */}
      <p className="sr-only" aria-live="polite">
        {details.message}
      </p>

      <ProjectGridControls
        search={grid.search}
        searchControl={grid.searchControl}
        controlsStatus={grid.controlsStatus}
        searchPlaceholder={grid.searchPlaceholder}
        searchLabel={grid.searchLabel}
        filterControls={grid.filterControls}
        onSearchChange={grid.onSearchChange}
        pageControls={
          grid.sortOptions ? null : <PageControls grid={grid} onToggleAllDetails={details.toggleAllDetails} />
        }
        searchInputRef={searchInputRef}
      />

      {grid.toolbarPlacement === 'top' ? toolbarElement : null}

      {grid.loading ? (
        // Focusable from script: it holds focus while Try again loads the rows (useRetryFocus).
        <p ref={loadingRef} className="project-grid-state project-grid-state-loading" role="status" tabIndex={-1}>
          Loading project data...
        </p>
      ) : null}
      {grid.error ? (
        <div className="project-grid-load-error">
          <p className="project-grid-state project-grid-state-error itg-error" role="alert">
            {grid.error}
          </p>
          {onRetry ? (
            <button
              ref={retryRef}
              type="button"
              className="itg-btn itg-btn-outline"
              onClick={() => retry(onRetry)}
            >
              Try again
            </button>
          ) : null}
        </div>
      ) : null}

      {!grid.loading && !grid.error ? (
        <ProjectGridResults
          grid={grid}
          details={details}
          searchInputRef={searchInputRef}
          countRef={countRef}
          emptyRef={emptyRef}
        />
      ) : null}

      {grid.toolbarPlacement === 'bottom' ? toolbarElement : null}
    </div>
  );
};
