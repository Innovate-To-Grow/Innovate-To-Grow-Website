import {useMemo, useState} from 'react';
import {ProjectGridTable} from './ProjectGridTable';
import type {ProjectRowsExporter} from './export/exportTypes';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  stripProjectGridItem,
  type ProjectGridItem,
} from './projectGrid';
import {PastProjectsDialog} from './builder/PastProjectsDialog';

interface MergedResultsTableProps {
  rows: ProjectGridItem[];
  onDeleteRow?: (row: ProjectGridItem) => void;
  onDeleteRows?: (rows: ProjectGridItem[]) => void;
  canUndoRows?: boolean;
  onUndoRows?: () => void;
  onResetRows?: () => void;
}

type ProjectRowsExportFormat = 'pdf' | 'excel' | 'word';

async function loadProjectRowsExporter(format: ProjectRowsExportFormat): Promise<ProjectRowsExporter> {
  switch (format) {
    case 'pdf':
      return (await import('./export/pdfExport')).exportProjectRowsPdf;
    case 'excel':
      return (await import('./export/excelExport')).exportProjectRowsExcel;
    case 'word':
      return (await import('./export/wordExport')).exportProjectRowsWord;
  }
}

export const MergedResultsTable = ({
  rows,
  onDeleteRow,
  onDeleteRows,
  canUndoRows = false,
  onUndoRows,
  onResetRows,
}: MergedResultsTableProps) => {
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
  });
  const [statusMessage, setStatusMessage] = useState('');
  const [isResetDialogOpen, setIsResetDialogOpen] = useState(false);
  const canBulkRemove = Boolean(onDeleteRows);
  const visibleRows = useMemo(() => table.sortedRows.map(stripProjectGridItem), [table.sortedRows]);

  const handleExport = async (format: ProjectRowsExportFormat, label: string) => {
    try {
      const exporter = await loadProjectRowsExporter(format);
      await exporter(visibleRows, 'past-projects', {title: 'Saved Merged Results'});
    } catch {
      setStatusMessage(`Unable to export ${label}. Please try again.`);
    }
  };

  const handleRemoveSelectedRows = () => {
    if (!onDeleteRows || !table.hasSelection) return;
    onDeleteRows(table.selectedRows);
    table.clearSelection();
  };

  const handleConfirmReset = () => {
    onResetRows?.();
    setIsResetDialogOpen(false);
  };

  return (
    <section className="project-grid-card">
      <div className="project-grid-card-header">
        <div>
          <h2 className="project-grid-card-title">Saved Merged Results</h2>
          <p className="project-grid-card-copy">
            Save rows from your search tables into one curation, then review or export it.
          </p>
        </div>
      </div>

      <ProjectGridTable
        columns={PAST_PROJECT_GRID_COLUMNS}
        rows={rows}
        pagedRows={table.pagedRows}
        filteredCount={table.filteredRows.length}
        totalCount={rows.length}
        search={table.search}
        searchPlaceholder="Search merged results..."
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
        emptyMessage="No merged results saved yet."
        countLabel="results"
        onDeleteRow={onDeleteRow}
        selectable={canBulkRemove}
        selectedKeys={table.selectedKeys}
        selectAllStateRows={table.filteredRows}
        onToggleSelected={table.toggleSelected}
        onToggleSelectAll={() => {
          const visible = table.filteredRows;
          const allVisibleSelected =
            visible.length > 0 && visible.every((row) => table.selectedKeys.has(row.__key));
          if (allVisibleSelected) {
            table.clearSelection();
          } else {
            table.selectRows(visible);
          }
        }}
        toolbarPlacement="bottom"
        toolbar={
          <div className="project-grid-inline-actions project-grid-inline-actions--clustered">
            <div className="project-grid-toolbar-cluster" aria-label="Export">
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void handleExport('pdf', 'PDF')}
                disabled={!visibleRows.length}
              >
                PDF
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void handleExport('excel', 'Excel')}
                disabled={!visibleRows.length}
              >
                Excel
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void handleExport('word', 'Microsoft Word')}
                disabled={!visibleRows.length}
              >
                Microsoft Word
              </button>
            </div>
            {onUndoRows || onResetRows || canBulkRemove ? (
              <div className="project-grid-toolbar-cluster" aria-label="Recovery">
                {canBulkRemove ? (
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={handleRemoveSelectedRows}
                    disabled={!table.hasSelection}
                  >
                    Remove Selected
                  </button>
                ) : null}
                {onUndoRows ? (
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={onUndoRows}
                    disabled={!canUndoRows}
                  >
                    Undo Merged Change
                  </button>
                ) : null}
                {onResetRows ? (
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() => setIsResetDialogOpen(true)}
                    disabled={!rows.length}
                  >
                    Reset Merged Results
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        }
      />

      {isResetDialogOpen ? (
        <PastProjectsDialog
          title="Reset merged results?"
          confirmLabel="Reset Merged Results"
          onCancel={() => setIsResetDialogOpen(false)}
          onConfirm={handleConfirmReset}
        >
          <p>Clear every project from the saved merged results? You can undo this immediately afterward.</p>
        </PastProjectsDialog>
      ) : null}

      {statusMessage ? <p className="project-grid-status">{statusMessage}</p> : null}
    </section>
  );
};
