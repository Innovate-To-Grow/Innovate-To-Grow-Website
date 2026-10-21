import {useId, useMemo} from 'react';
import {Link, useSearchParams} from 'react-router';
import {useProjectGridFilters, type ProjectGridFilterOption} from '../hooks/useProjectGridFilters';
import {ProjectGridTable, type ProjectGridSortOption} from './ProjectGridTable';
import {
  PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  formatTermForProse,
  getPredominantTerm,
  type ProjectGridRow,
} from './projectGrid';
import {pluralize} from './saveResults';
import {useProjectGridTable} from './useProjectGridTable';

const CURRENT_SORT_OPTIONS: ProjectGridSortOption[] = [
  {field: 'class_code', label: 'Team number'},
  {field: 'project_title', label: 'Project title'},
  {field: 'organization', label: 'Organization'},
];

interface FilterSelectProps {
  label: string;
  allLabel: string;
  value: string;
  options: ProjectGridFilterOption[];
  onChange: (value: string) => void;
}

const FilterSelect = ({label, allLabel, value, options, onChange}: FilterSelectProps) => {
  const selectId = useId();
  return (
    <div className="itg-field project-grid-filter">
      <label className="project-grid-field-label" htmlFor={selectId}>
        {label}
      </label>
      <select
        id={selectId}
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
};

interface CurrentProjectsFiltersProps {
  filters: ReturnType<typeof useProjectGridFilters>;
  changeFilter: (setter: (value: string) => void) => (value: string) => void;
}

/** The Class and Industry selects. */
const CurrentProjectsFilters = ({filters, changeFilter}: CurrentProjectsFiltersProps) => (
  <>
    <FilterSelect
      label="Class"
      allLabel="All classes"
      value={filters.classCode}
      options={filters.classOptions}
      onChange={changeFilter(filters.setClassCode)}
    />
    <FilterSelect
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
  /** Class names by code, from the schedule. */
  classLabels?: Record<string, string>;
  /** Key prefix for the grid rows. */
  namespace: string;
  emptyMessage: string;
  /** 'teams' on the presenting-teams page, whose rows are all presenting. */
  countLabel?: 'projects' | 'teams';
}

/** Body of /current-projects and /presenting-teams: title, meta line, lede, filters and the project table. */
export const CurrentProjectsView = ({
  title,
  lede,
  rows,
  loading,
  error,
  classLabels,
  namespace,
  emptyMessage,
  countLabel = 'projects',
}: CurrentProjectsViewProps) => {
  const [searchParams] = useSearchParams();
  const items = useMemo(() => createProjectGridItems(rows, namespace), [rows, namespace]);
  const filters = useProjectGridFilters(items, classLabels);
  const table = useProjectGridTable({
    rows: items,
    defaultSortField: 'class_code',
    defaultSortDirection: 'asc',
    initialSearch: searchParams.get('value') || '',
    filterRow: filters.filterRow,
  });

  const query = table.search.trim();

  const changeFilter = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    table.setPage(0);
  };

  return (
    <div className="projects-page">
      <h1 className="itg-page-title">{title}</h1>
      {!loading && !error && rows.length ? (
        <p className="itg-page-meta">{metaLine(rows, countLabel)}</p>
      ) : null}
      <p className="itg-lead">{lede}</p>

      <ProjectGridTable
        columns={PROJECT_GRID_COLUMNS}
        rows={items}
        pagedRows={table.pagedRows}
        filteredCount={table.filteredRows.length}
        totalCount={items.length}
        search={table.search}
        searchPlaceholder="Team, project, organization…"
        filterControls={<CurrentProjectsFilters filters={filters} changeFilter={changeFilter} />}
        sortOptions={CURRENT_SORT_OPTIONS}
        sortField={table.sortField}
        sortDirection={table.sortDirection}
        onSearchChange={(value) => {
          table.setSearch(value);
          table.setPage(0);
        }}
        onSortChange={table.toggleSort}
        onClearFilters={filters.clear}
        noResultsHint="Older projects are in Past Projects."
        noResultsHeadingLevel={2}
        noResultsActions={
          query ? (
            <Link className="itg-link" to={`/past-projects?value=${encodeURIComponent(query)}`}>
              Search Past Projects for “{query}”
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
        emptyMessage={emptyMessage}
        countLabel={countLabel}
        linkScope="current"
      />
    </div>
  );
};
