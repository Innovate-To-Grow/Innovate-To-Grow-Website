import {useMemo, useCallback} from 'react';
import {useSearchParams} from 'react-router-dom';
import {ProjectGridTable, ProjectImport, CURRENT_PROJECT_GRID_COLUMNS, createProjectGridItems, useProjectGridTable} from '../../components/Projects';
import {useCurrentProjectGridData} from '../../hooks/useProjectGridData';
import {getStoredUser} from '../../services/auth';
import './ProjectsPage.css';

export const ProjectsPage = () => {
  const {rows, loading, error, refetch} = useCurrentProjectGridData();
  const [searchParams] = useSearchParams();
  const items = useMemo(() => createProjectGridItems(rows, 'current-projects'), [rows]);
  const table = useProjectGridTable({
    rows: items,
    pageSize: 10,
    defaultSortField: 'class_code',
    defaultSortDirection: 'asc',
    initialSearch: searchParams.get('value') || '',
  });

  const user = getStoredUser();
  const isStaff = user?.is_staff === true;

  const handleImportComplete = useCallback(() => {
    refetch();
  }, [refetch]);

  return (
    <div className="projects-page">
      <header className="projects-page-hero">
        <h1 className="projects-page-title">Current Projects</h1>
        <p className="projects-page-lead">
          Browse the current Innovate to Grow projects, search by team or organization, and expand rows to view abstracts and student names.
        </p>
      </header>

      {isStaff && (
        <section className="projects-page-card">
          <ProjectImport onImportComplete={handleImportComplete} />
        </section>
      )}

      <section className="projects-page-card">
        <ProjectGridTable
          columns={CURRENT_PROJECT_GRID_COLUMNS}
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
          page={table.page}
          totalPages={table.totalPages}
          onPageChange={table.setPage}
          loading={loading}
          error={error}
          emptyMessage="No current projects are available yet."
          countLabel="projects"
        />
      </section>
    </div>
  );
};
