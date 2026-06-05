import {useEffect, useState} from 'react';
import {useAuth} from '@/features/auth';
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
  note?: string;
  onCreateShare?: (rows: ProjectGridRow[], note: string) => Promise<string>;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

export const MergedResultsTable = ({
  rows,
  sharedMode = false,
  title = 'Saved Merged Results',
  note,
  onCreateShare,
  onDeleteRow,
}: MergedResultsTableProps) => {
  const {isAuthenticated} = useAuth();
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    expandAllByDefault: sharedMode,
  });
  const [shareUrl, setShareUrl] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isSharing, setIsSharing] = useState(false);
  const [noteDraft, setNoteDraft] = useState('');

  useEffect(() => {
    if (sharedMode) {
      setShareUrl(window.location.href);
    }
  }, [sharedMode]);

  const visibleRows = table.sortedRows.map(stripProjectGridItem);
  const canShare = !sharedMode && Boolean(onCreateShare) && isAuthenticated;
  const sharedNote = sharedMode ? (note ?? '').trim() : '';

  const handleCreateShare = async () => {
    if (!onCreateShare || !visibleRows.length) {
      return;
    }

    setIsSharing(true);
    setStatusMessage('');
    try {
      const nextShareUrl = await onCreateShare(visibleRows, noteDraft.trim());
      setShareUrl(nextShareUrl);
      setStatusMessage('Shareable URL is ready.');
      window.open(nextShareUrl, '_blank', 'noopener,noreferrer');
    } catch {
      setStatusMessage('Unable to create a shareable URL. Please try again.');
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

      {sharedNote ? (
        <div className="project-grid-shared-note">
          <p className="project-grid-shared-note-label">Note</p>
          <p className="project-grid-shared-note-text">{sharedNote}</p>
        </div>
      ) : null}

      {!sharedMode && onCreateShare ? (
        isAuthenticated ? (
          <div className="project-grid-share-note">
            <label className="project-grid-share-note-label" htmlFor="past-project-share-note">
              Add a note (shown at the top of the shared page)
            </label>
            <textarea
              id="past-project-share-note"
              className="project-grid-share-note-input"
              value={noteDraft}
              maxLength={2000}
              rows={3}
              placeholder="Optional — add context for whoever opens the shared link."
              onChange={(event) => setNoteDraft(event.target.value)}
            />
          </div>
        ) : (
          <p className="project-grid-share-login-hint">
            <a href="/login">Log in</a> to create a shareable link.
          </p>
        )
      ) : null}

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
        onDeleteRow={sharedMode ? undefined : onDeleteRow}
        toolbar={
          <div className="project-grid-inline-actions project-grid-inline-actions--clustered">
            <div className="project-grid-toolbar-cluster" aria-label="Export">
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void exportProjectRowsCsv(visibleRows, 'past-projects')}
                disabled={!visibleRows.length}
              >
                CSV
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void exportProjectRowsExcel(visibleRows, 'past-projects')}
                disabled={!visibleRows.length}
              >
                Excel
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void exportProjectRowsPdf(visibleRows, 'past-projects', title)}
                disabled={!visibleRows.length}
              >
                PDF
              </button>
            </div>
            <div className="project-grid-toolbar-cluster" aria-label="Share link">
              {canShare ? (
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
          </div>
        }
      />

      {statusMessage ? <p className="project-grid-status">{statusMessage}</p> : null}
    </section>
  );
};
