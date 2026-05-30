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
      <h2 className="project-grid-card-title">Search Tables</h2>
    </div>

    <div className="past-projects-action-bar-controls">
      <div className="past-projects-action-bar-group" aria-label="Tables and merge">
        <button type="button" className="itg-btn itg-btn-primary" onClick={onAddSearchTable} disabled={loading || Boolean(error)}>
          + Search Table
        </button>
        <button type="button" className="itg-btn itg-btn-outline" onClick={onMergeResults} disabled={!searchTableCount}>
          Save/Merge Results
        </button>
      </div>
      <div className="past-projects-action-bar-group" aria-label="Selection and delete mode">
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
    </div>

    <details className="past-projects-help-details">
      <summary className="past-projects-help-summary">More help: buttons, merge, tables &amp; delete mode</summary>
      <p className="past-projects-help-intro">
        The row of buttons above runs the main workflow. Expand this section for a full walkthrough of what each action
        does, how merge combines tables, and how delete mode differs from deleting rows inside a table.
      </p>
      <div className="past-projects-help-grid">
        <div className="project-grid-help-card">
          <strong>+ Search Table</strong>
          <span>
            Adds another blank search table. Each table loads the full past-project archive on its own, so you can try
            different filters side by side (for example, one table for a class code and another for an organization).
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>Save/Merge Results</strong>
          <span>
            Sends the <em>visible</em> rows from <strong>every open search table</strong> into{' '}
            <strong>Saved Merged Results</strong> below. Only rows that pass the search box and appear in the grid are
            included. If the same project appears in more than one table, it is stored once. Merging does not remove
            search tables—you can merge again after changing filters.
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>Delete Selected Rows / Keep Selected Rows</strong>
          <span>
            Runs on <strong>every open search table</strong> in one step. In each table, <strong>Delete Selected Rows</strong>{' '}
            removes the rows you checked; <strong>Keep Selected Rows</strong> removes every row that is <em>not</em>{' '}
            checked so only checked rows remain. Tables with no checkboxes selected are left unchanged. You need at
            least one checkbox selected anywhere before these buttons are enabled.
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>Delete Table (checkbox)</strong>
          <span>
            When enabled, each search table shows a red overlay. Click the overlay on a table to remove that entire
            card from the page. This does <strong>not</strong> delete rows already in Saved Merged Results. Turn the
            checkbox off when you are done so you do not remove a table by mistake.
          </span>
        </div>
        <div className="project-grid-help-card project-grid-help-card--wide">
          <strong>Inside each table</strong>
          <span>
            Use the search field, click column headers to sort, and change <strong>Per page</strong> if you want more
            rows at once. Open <strong>View</strong> on a row to read abstracts and student names when available. Use
            the table toolbar for “Select all entries”, “Deselect”, and “Show / Hide all details” for that table only.
          </span>
        </div>
      </div>
    </details>

    {builderMessage ? <p className="project-grid-status">{builderMessage}</p> : null}
  </div>
);
