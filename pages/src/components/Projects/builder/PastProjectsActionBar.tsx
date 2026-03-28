interface PastProjectsActionBarProps {
  builderMessage: string;
  error: string | null;
  hasAnySelection: boolean;
  loading: boolean;
  searchTableCount: number;
  deleteMode: boolean;
  onAddSearchTable: () => void;
  onMergeResults: () => void;
  onDeleteSelectedRows: () => void;
  onKeepSelectedRows: () => void;
  onDeleteModeChange: (checked: boolean) => void;
}

export const PastProjectsActionBar = ({
  builderMessage,
  error,
  hasAnySelection,
  loading,
  searchTableCount,
  deleteMode,
  onAddSearchTable,
  onMergeResults,
  onDeleteSelectedRows,
  onKeepSelectedRows,
  onDeleteModeChange,
}: PastProjectsActionBarProps) => (
  <div className="project-grid-card past-projects-action-bar">
    <div className="project-grid-card-header">
      <div>
        <h2 className="project-grid-card-title">Search Tables</h2>
        <p className="project-grid-card-copy">
          Open one or more search tables, narrow the dataset independently, then merge the remaining rows into saved
          results.
        </p>
      </div>
    </div>

    <div className="past-projects-action-bar-controls">
      <button type="button" className="itg-btn itg-btn-primary" onClick={onAddSearchTable} disabled={loading || Boolean(error)}>
        + Search Table
      </button>
      <button type="button" className="itg-btn itg-btn-outline" onClick={onMergeResults} disabled={!searchTableCount}>
        Save/Merge Results
      </button>
      <button type="button" className="itg-btn itg-btn-outline" onClick={onDeleteSelectedRows} disabled={!hasAnySelection}>
        Delete Selected Rows
      </button>
      <button type="button" className="itg-btn itg-btn-outline" onClick={onKeepSelectedRows} disabled={!hasAnySelection}>
        Keep Selected Rows
      </button>
      <label className="past-projects-delete-toggle">
        <input type="checkbox" checked={deleteMode} onChange={(event) => onDeleteModeChange(event.target.checked)} />
        Delete Table
      </label>
    </div>

    <div className="past-projects-help-grid">
      <div className="project-grid-help-card">
        <strong>How merge works</strong>
        <span>Each search table contributes only its currently filtered rows. Duplicate rows are skipped automatically.</span>
      </div>
      <div className="project-grid-help-card">
        <strong>Delete mode</strong>
        <span>Turn on Delete Table, then click the red overlay on any search table you want to remove.</span>
      </div>
    </div>

    {builderMessage ? <p className="project-grid-status">{builderMessage}</p> : null}
  </div>
);
