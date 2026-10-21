import './projects.css';
import {ProjectGridControls, PageSizeField} from './grid/ProjectGridControls';
import {ProjectGridDesktopTable} from './grid/ProjectGridDesktopTable';
import {ProjectGridMobileCards} from './grid/ProjectGridMobileCards';
import {ProjectGridPager} from './grid/ProjectGridPager';
import {ProjectGridNoResults, ProjectGridResultsBar} from './grid/ProjectGridResults';
import type {ProjectGridTableProps} from './grid/gridTableProps';

export type {ProjectGridSortOption} from './grid/gridTableProps';

function withGridDefaults({
  searchPlaceholder = 'Search projects...',
  searchLabel = 'Search',
  noResultsHeadingLevel = 2,
  allDetailsExpanded = false,
  emptyMessage = 'No projects found.',
  countLabel = 'projects',
  toolbarPlacement = 'top',
  linkScope = 'current',
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
    selectable,
    selectedKeys,
    deleteDisabled,
    loadMissingDetails,
  };
}

type ResolvedGridProps = ReturnType<typeof withGridDefaults>;

/** Per page and View All Details: in the filter well, or beside the sort select when there is one. */
const PageControls = ({grid}: {grid: ResolvedGridProps}) => (
  <>
    <PageSizeField value={grid.pageSize} options={grid.pageSizeOptions} onChange={grid.onPageSizeChange} />
    {grid.onToggleAllDetails ? (
      <button
        type="button"
        className={`itg-btn ${grid.sortOptions ? 'itg-btn-text' : 'itg-btn-outline'} project-grid-toggle-details`}
        onClick={grid.onToggleAllDetails}
      >
        {grid.allDetailsExpanded ? 'Hide All Details' : 'View All Details'}
      </button>
    ) : null}
  </>
);

/** Everything below the filter well once the rows are loaded: counts, empty states, the rows and the pager. */
const ProjectGridResults = ({grid}: {grid: ResolvedGridProps}) => {
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
    onToggleExpanded: grid.onToggleExpanded,
    onDeleteRow: grid.onDeleteRow,
    deleteDisabled: grid.deleteDisabled,
    loadMissingDetails: grid.loadMissingDetails,
    isRowSaved: grid.isRowSaved,
    savedRowLabel: grid.savedRowLabel,
    highlightedKeys: grid.highlightedKeys,
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
          onSortChange={grid.onSortChange}
          query={query}
          countLabel={grid.countLabel}
          pageControls={<PageControls grid={grid} />}
        />
      ) : null}

      {grid.totalCount === 0 ? <p className="project-grid-empty">{grid.emptyMessage}</p> : null}

      {noResults ? (
        <ProjectGridNoResults
          query={query}
          countLabel={grid.countLabel}
          headingLevel={grid.noResultsHeadingLevel}
          noResultsHint={grid.noResultsHint}
          noResultsActions={grid.noResultsActions}
          onClear={() => {
            grid.onSearchChange('');
            grid.onClearFilters?.();
          }}
        />
      ) : null}

      {grid.totalCount > 0 && !noResults ? (
        <>
          <ProjectGridDesktopTable
            {...rowProps}
            rows={grid.rows}
            selectAllStateRows={grid.selectAllStateRows}
            onToggleSelectAll={grid.onToggleSelectAll}
            sortField={grid.sortField}
            sortDirection={grid.sortDirection}
            onSortChange={grid.onSortChange}
          />
          <ProjectGridMobileCards {...rowProps} />
        </>
      ) : null}

      {grid.totalPages > 1 ? (
        <ProjectGridPager page={grid.page} totalPages={grid.totalPages} onPageChange={grid.onPageChange} />
      ) : null}
    </>
  );
};

/**
 * The projects grid: a filter well, an optional toolbar, the results (a table on wide screens, cards on
 * phones) and the pager. Paging, sorting and selection state come from `useProjectGridTable`.
 */
export const ProjectGridTable = (props: ProjectGridTableProps) => {
  const grid = withGridDefaults(props);
  const toolbarElement = grid.toolbar ? (
    <div className={`project-grid-toolbar${grid.toolbarPlacement === 'bottom' ? ' project-grid-toolbar--bottom' : ''}`}>
      {grid.toolbar}
    </div>
  ) : null;

  return (
    <div className="project-grid-table-shell">
      <ProjectGridControls
        search={grid.search}
        searchControl={grid.searchControl}
        controlsStatus={grid.controlsStatus}
        searchPlaceholder={grid.searchPlaceholder}
        searchLabel={grid.searchLabel}
        filterControls={grid.filterControls}
        onSearchChange={grid.onSearchChange}
        pageControls={grid.sortOptions ? null : <PageControls grid={grid} />}
      />

      {grid.toolbarPlacement === 'top' ? toolbarElement : null}

      {grid.loading ? <p className="project-grid-state">Loading project data...</p> : null}
      {grid.error ? (
        <p className="project-grid-state project-grid-state-error itg-error" role="alert">
          {grid.error}
        </p>
      ) : null}

      {!grid.loading && !grid.error ? <ProjectGridResults grid={grid} /> : null}

      {grid.toolbarPlacement === 'bottom' ? toolbarElement : null}
    </div>
  );
};
