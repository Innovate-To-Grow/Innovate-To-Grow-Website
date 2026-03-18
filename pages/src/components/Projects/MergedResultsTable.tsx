import {useEffect, useState} from 'react';
import {ProjectGridTable} from './ProjectGridTable';
import {exportProjectRowsCsv, exportProjectRowsExcel, exportProjectRowsPdf} from './projectGridExport';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

interface MergedResultsTableProps {
  rows: ProjectGridItem[];
  sharedMode?: boolean;
  title?: string;
  onCreateShare?: (rows: ProjectGridRow[]) => Promise<string>;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

export const MergedResultsTable = ({
  rows,
  sharedMode = false,
  title = 'Saved Merged Results',
  onCreateShare,
  onDeleteRow,
}: MergedResultsTableProps) => {
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
  });
  const [shareUrl, setShareUrl] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isSharing, setIsSharing] = useState(false);

  useEffect(() => {
    if (sharedMode) {
      setShareUrl(window.location.href);
    }
  }, [sharedMode]);

  const visibleRows = table.sortedRows.map(stripProjectGridItem);

  const handleCreateShare = async () => {
    if (!onCreateShare || !visibleRows.length) {
      return;
    }

    setIsSharing(true);
    setStatusMessage('');
    try {
      const nextShareUrl = await onCreateShare(visibleRows);
      setShareUrl(nextShareUrl);
      setStatusMessage('Shareable URL is ready.');
      window.open(nextShareUrl, '_blank', 'noopener,noreferrer');
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : 'Unable to create a shareable URL.');
    } finally {
      setIsSharing(false);
    }
  };

  const handleCopyUrl = async () => {
    if (!shareUrl) {
      return;
    }
    await navigator.clipboard.writeText(shareUrl);
    setStatusMessage('URL copied to clipboard.');
  };

  return (
    <section className="project-grid-card">
      <div className="project-grid-card-header">
        <div>
          <h2 className="project-grid-card-title">{title}</h2>
          <p className="project-grid-card-copy">
            {sharedMode
              ? 'Browse the saved merged results from this shared link.'
              : 'Merge filtered search tables into one saved result set, then export or share it.'}
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
        sortField={table.sortField}
        sortDirection={table.sortDirection}
        onSearchChange={table.setSearch}
        onSortChange={table.toggleSort}
        expandedKeys={table.expandedKeys}
        onToggleExpanded={table.toggleExpanded}
        page={table.page}
        totalPages={table.totalPages}
        onPageChange={table.setPage}
        emptyMessage="No merged results saved yet."
        countLabel="results"
        onDeleteRow={sharedMode ? undefined : onDeleteRow}
        toolbar={
          <div className="project-grid-inline-actions">
            <button type="button" className="itg-btn itg-btn-outline" onClick={table.toggleAllDetails}>
              {table.allDetailsExpanded ? 'Hide Details' : 'Show Details'}
            </button>
            <button
              type="button"
              className="itg-btn itg-btn-outline"
              onClick={() => exportProjectRowsCsv(visibleRows, 'past-projects')}
              disabled={!visibleRows.length}
            >
              CSV
            </button>
            <button
              type="button"
              className="itg-btn itg-btn-outline"
              onClick={() => exportProjectRowsExcel(visibleRows, 'past-projects')}
              disabled={!visibleRows.length}
            >
              Excel
            </button>
            <button
              type="button"
              className="itg-btn itg-btn-outline"
              onClick={() => exportProjectRowsPdf(visibleRows, 'past-projects', title)}
              disabled={!visibleRows.length}
            >
              PDF
            </button>
            {!sharedMode && onCreateShare ? (
              <button
                type="button"
                className="itg-btn itg-btn-primary"
                onClick={() => void handleCreateShare()}
                disabled={!visibleRows.length || isSharing}
              >
                {isSharing ? 'Creating URL...' : 'Get Shareable URL'}
              </button>
            ) : null}
            <button
              type="button"
              className="itg-btn itg-btn-outline"
              onClick={() => void handleCopyUrl()}
              disabled={!shareUrl}
            >
              Copy URL
            </button>
          </div>
        }
      />

      {statusMessage ? <p className="project-grid-status">{statusMessage}</p> : null}
    </section>
  );
};
