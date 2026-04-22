import {useMemo} from 'react';
import {useSearchParams} from 'react-router-dom';
import {ProjectGridTable, PROJECT_GRID_COLUMNS, createProjectGridItems, useProjectGridTable} from '../../components/Projects';
import {useCurrentProjectGridData} from '../../hooks/useProjectGridData';

export const PresentingTeamsPage = () => {
  const {rows, loading, error} = useCurrentProjectGridData();
  const [searchParams] = useSearchParams();
  const presentingRows = useMemo(() => rows.filter((r) => r.is_presenting === 'Yes'), [rows]);
  const items = useMemo(() => createProjectGridItems(presentingRows, 'presenting-teams'), [presentingRows]);
  const table = useProjectGridTable({
    rows: items,
    defaultSortField: 'class_code',
    defaultSortDirection: 'asc',
    initialSearch: searchParams.get('value') || '',
  });

  return (
    <div className="projects-page">
      <header className="projects-page-hero">
        <h1 className="projects-page-title">Presenting Teams</h1>
        <p className="projects-page-lead">
          Teams presenting at this semester&apos;s Innovate to Grow showcase. Search by team, class, or organization and expand rows for abstracts and student names.
        </p>
      </header>

      <section className="projects-page-card">
        <ProjectGridTable
          columns={PROJECT_GRID_COLUMNS}
          rows={items}
          pagedRows={table.pagedRows}
          filteredCount={table.filteredRows.length}
          totalCount={items.length}
          search={table.search}
          sortField={table.sortField}
          sortDirection={table.sortDirection}
          onSearchChange={table.setSearch}
          onSortChange={table.toggleSort}
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
          emptyMessage="No presenting teams are available yet."
          countLabel="teams"
        />
      </section>
    </div>
  );
};
