import {useId, useMemo, type ReactNode} from 'react';
import {Link} from 'react-router';
import {useProjectGridFilters, type ProjectGridFilterOption} from '../../../hooks/useProjectGridFilters';
import {useListScrollPosition} from '../../../hooks/useListScrollPosition';
import {
  PROJECT_LIST_URL_DEFAULTS,
  useInitialProjectListUrlState,
  useProjectListStateKey,
  useProjectListUrlSync,
} from '../../../hooks/useProjectListUrlState';
import {ProjectGridTable, type ProjectGridSortOption} from '../../grid/table/ProjectGridTable';
import {
  PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  formatTermForProse,
  getPredominantTerm,
  type ProjectGridItem,
  type ProjectGridRow,
} from '../../grid/contracts/projectGrid';
import {pluralize} from '../../shared/utils/saveResults';
import {useProjectGridTable} from '../../grid/state/useProjectGridTable';
import {ActiveFilterChips} from './ActiveFilterChips';

const CURRENT_SORT_OPTIONS: ProjectGridSortOption[] = [
  {field: 'class_code', label: 'Team number'},
  {field: 'project_title', label: 'Project title'},
  {field: 'organization', label: 'Organization'},
];

interface FilterSelectProps {
  /** The select's id: the filter chips focus it when its chip goes (ActiveFilterChips). */
  id: string;
  label: string;
  allLabel: string;
  value: string;
  options: ProjectGridFilterOption[];
  onChange: (value: string) => void;
}

const FilterSelect = ({id, label, allLabel, value, options, onChange}: FilterSelectProps) => (
  <div className="itg-field project-grid-filter">
    <label className="project-grid-field-label" htmlFor={id}>
      {label}
    </label>
    <select
      id={id}
      className="itg-select project-grid-select"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{allLabel}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  </div>
);

interface CurrentProjectsFiltersProps {
  filters: ReturnType<typeof useProjectGridFilters>;
  changeFilter: (setter: (value: string) => void) => (value: string) => void;
  selectIds: {class: string; industry: string};
}

/** The Class and Industry selects. */
const CurrentProjectsFilters = ({filters, changeFilter, selectIds}: CurrentProjectsFiltersProps) => (
  <>
    <FilterSelect
      id={selectIds.class}
      label="Class"
      allLabel="All classes"
      value={filters.classCode}
      options={filters.classOptions}
      onChange={changeFilter(filters.setClassCode)}
    />
    <FilterSelect
      id={selectIds.industry}
      label="Industry"
      allLabel="All industries"
      value={filters.industry}
      options={filters.industryOptions}
      onChange={changeFilter(filters.setIndustry)}
    />
  </>
);

/** The line under the title: the term, the count, and how many teams present. */
const metaLine = (rows: ProjectGridRow[], countLabel: 'projects' | 'teams') => {
  const term = formatTermForProse(getPredominantTerm(rows));
  const presentingCount = rows.filter((row) => row.is_presenting === 'Yes').length;
  const meta =
    countLabel === 'teams'
      ? [term, `${pluralize(rows.length, 'team')} presenting`]
      : [
          term,
          pluralize(rows.length, 'project'),
          presentingCount ? `${pluralize(presentingCount, 'team')} presenting at the showcase` : '',
        ];
  return meta.filter(Boolean).join(' · ');
};

interface CurrentProjectsViewProps {
  title: string;
  lede: string;
  rows: ProjectGridRow[];
  loading: boolean;
  error: string | null;
  /** Loads the projects again after `error`. */
  onRetry?: () => void;
  /** Class names by code, from the schedule. */
  classLabels?: Record<string, string>;
  /** Key prefix for the grid rows. */
  namespace: string;
  /** The empty state's heading, text and action, when the schedule has no rows (ProjectGridTable). */
  emptyTitle: string;
  emptyMessage: string;
  emptyActions?: ReactNode;
  /** 'teams' on the presenting-teams page, whose rows are all presenting. */
  countLabel?: 'projects' | 'teams';
}

type CurrentProjectsGridProps = Omit<CurrentProjectsViewProps, 'title' | 'lede' | 'rows' | 'namespace'> & {
  /** The page title, which names the table. */
  tableLabel: string;
  items: ProjectGridItem[];
  /** The rows are loaded and shown: the grid's state can be written to the URL. */
  ready: boolean;
};

/**
 * The filters and the project table. Search, filters, sort and page start from the URL and are written back to
 * it, so Back from a project page, a reload or a shared link shows the same view.
 */
const CurrentProjectsGrid = ({
  tableLabel,
  items,
  ready,
  loading,
  error,
  onRetry,
  classLabels,
  countLabel = 'projects',
  ...emptyState
}: CurrentProjectsGridProps) => {
  const initial = useInitialProjectListUrlState();
  const selectIds = {class: useId(), industry: useId()};
  const filters = useProjectGridFilters(items, classLabels, initial);
  const table = useProjectGridTable({
    rows: items,
    pageSize: initial.pageSize,
    defaultSortField: PROJECT_LIST_URL_DEFAULTS.sortField,
    defaultSortDirection: PROJECT_LIST_URL_DEFAULTS.sortDirection,
    initialSortField: initial.sortField,
    initialSortDirection: initial.sortDirection,
    initialPage: initial.page,
    initialSearch: initial.search,
    filterRow: filters.filterRow,
    classLabels,
  });
  useProjectListUrlSync(
    {
      search: table.search,
      classCode: filters.classCode,
      industry: filters.industry,
      sortField: table.sortField,
      sortDirection: table.sortDirection,
      page: table.page,
      pageSize: table.pageSize,
    },
    ready,
  );

  const query = table.search.trim();

  const changeFilter = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    table.setPage(0);
  };

  return (
    <ProjectGridTable
      tableLabel={tableLabel}
      columns={PROJECT_GRID_COLUMNS}
      rows={items}
      pagedRows={table.pagedRows}
      filteredCount={table.filteredRows.length}
      totalCount={items.length}
      search={table.search}
      searchPlaceholder="Project, team, organization, student…"
      filterControls={<CurrentProjectsFilters filters={filters} changeFilter={changeFilter} selectIds={selectIds} />}
      toolbar={
        filters.filterChips.length ? (
          <ActiveFilterChips
            filters={filters}
            changeFilter={changeFilter}
            selectIds={selectIds}
            noResults={table.filteredRows.length === 0}
          />
        ) : undefined
      }
      activeFilters={filters.activeLabels}
      sortOptions={CURRENT_SORT_OPTIONS}
      sortField={table.sortField}
      sortDirection={table.sortDirection}
      onSearchChange={table.setSearch}
      onSortChange={table.toggleSort}
      onSortSelect={table.setSort}
      onClearFilters={filters.clear}
      noResultsHint="Older projects are in Past Projects."
      noResultsHeadingLevel={2}
      noResultsActions={
        query ? (
          <Link className="itg-link" to={`/past-projects?value=${encodeURIComponent(query)}`}>
            {`Search Past Projects for “${query}”`}
          </Link>
        ) : null
      }
      expandedKeys={table.expandedKeys}
      onToggleExpanded={table.toggleExpanded}
      onToggleAllDetails={table.toggleAllDetails}
      allDetailsExpanded={table.allDetailsExpanded}
      page={table.page}
      totalPages={table.totalPages}
      onPageChange={table.setPage}
      pageSize={table.pageSize}
      pageSizeOptions={table.pageSizeOptions}
      onPageSizeChange={table.setPageSize}
      loading={loading}
      error={error}
      onRetry={onRetry}
      {...emptyState}
      countLabel={countLabel}
      linkScope="current"
    />
  );
};

/** Body of /current-projects and /presenting-teams: title, meta line, lede, filters and the project table. */
export const CurrentProjectsView = ({title, lede, rows, namespace, ...gridProps}: CurrentProjectsViewProps) => {
  const {loading, error, countLabel = 'projects'} = gridProps;
  const items = useMemo(() => createProjectGridItems(rows, namespace), [rows, namespace]);
  const ready = !loading && !error && items.length > 0;
  // A new key (a link to the list, or Back and Forward between two of its URLs) starts the grid over from the URL.
  const gridKey = useProjectListStateKey();
  useListScrollPosition(ready);
  const meta = ready ? metaLine(rows, countLabel) : '';

  return (
    // Marked so the chat launcher tucks away over the list's text and rows, not only its controls (useLauncherYield).
    <div className="projects-page" data-launcher-avoid="">
      <h1 className="itg-page-title" data-embed-section="page-header">{title}</h1>
      {/* Kept, blank, while the rows load: appearing later, the line pushed the lede and the grid down. */}
      <p className="itg-page-meta" data-embed-section="page-header" aria-hidden={meta ? undefined : true}>
        {meta || '\u00a0'}
      </p>
      <p className="itg-lead" data-embed-section="page-header">{lede}</p>
      <CurrentProjectsGrid key={gridKey} tableLabel={title} items={items} ready={ready} {...gridProps} />
    </div>
  );
};
