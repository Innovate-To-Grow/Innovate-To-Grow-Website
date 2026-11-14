import {useEffect, useRef, type RefObject} from 'react';
import {useMediaQuery} from '@/features/layout';
import {PageSizeField} from '../controls/ProjectGridControls';
import {ProjectGridDesktopTable} from '../rows/ProjectGridDesktopTable';
import {ProjectGridMobileCards} from '../rows/ProjectGridMobileCards';
import {ProjectGridPager} from '../controls/ProjectGridPager';
import {ProjectGridEmpty, ProjectGridNoResults, ProjectGridResultsBar} from './ProjectGridResults';
import {showResultsStart} from '../state/useResultsFocus';
import {
  abstractsSkippedBy,
  type DetailsAnnouncements,
  PHONE_LAYOUT_QUERY,
  type ResolvedGridProps,
  rowPropsFor,
} from './resolvedGridProps';

interface PageControlsProps {
  grid: ResolvedGridProps;
  /** Opens or closes every row's details and says so (useDetailsAnnouncements). */
  onToggleAllDetails: () => void;
}

/**
 * Per page and View All Details: in the filter well, or beside the sort select when there is one. The toggle is
 * the same outlined button in both places.
 */
export const PageControls = ({grid, onToggleAllDetails}: PageControlsProps) => (
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
  /** The filter well's search field, focused when "Clear Search" removes itself. */
  searchInputRef: RefObject<HTMLInputElement | null>;
  /** The count line: focus goes there after a page change, and after Try Again (see useRetryFocus). */
  countRef: RefObject<HTMLParagraphElement | null>;
  /** The empty state's heading (or message), which takes focus after Try Again when no rows came back. */
  emptyRef: RefObject<HTMLElement | null>;
}

/** Everything below the filter well once the rows are loaded: counts, empty states, the rows and the pager. */
export const ProjectGridResults = ({grid, details, searchInputRef, countRef, emptyRef}: ResultsProps) => {
  // Only the layout the screen shows is rendered: mounting both and hiding one with CSS doubled the rows (and their
  // opened details) that every sort, page change and "View All Details" had to render.
  const isPhone = useMediaQuery(PHONE_LAYOUT_QUERY);
  const pagerTarget = useRef<number | null>(null);
  const query = grid.search.trim();
  const noResults = grid.totalCount > 0 && grid.filteredCount === 0;
  const rowProps = rowPropsFor(grid, details);

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
          abstractsSkipped={abstractsSkippedBy(grid.serverSearch)}
          pageControls={<PageControls grid={grid} onToggleAllDetails={details.toggleAllDetails} />}
          countRef={countRef}
        />
      ) : null}

      {grid.totalCount === 0 ? (
        <ProjectGridEmpty
          emptyTitle={grid.emptyTitle}
          emptyMessage={grid.emptyMessage}
          emptyActions={grid.emptyActions}
          headingLevel={grid.noResultsHeadingLevel}
          emptyRef={emptyRef}
        />
      ) : null}

      {noResults ? (
        <ProjectGridNoResults
          query={query}
          countLabel={grid.countLabel}
          activeFilters={grid.activeFilters}
          headingLevel={grid.noResultsHeadingLevel}
          searching={grid.serverSearch?.pending}
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
