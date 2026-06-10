interface PastProjectsActionBarProps {
  aiSearchDisabled?: boolean;
  aiSearchLoginRequired?: boolean;
  builderMessage: string;
  error: string | null;
  hasAnySelection: boolean;
  loading: boolean;
  mergeButtonLabel?: string;
  searchTableCount: number;
  showHelp?: boolean;
  title?: string;
  onAddAISearchTable?: () => void;
  onAddSearchTable: () => void;
  onMergeResults: () => void;
  onDeleteSelectedRows: () => void;
  onKeepSelectedRows: () => void;
}

export const PastProjectsActionBar = ({
  aiSearchDisabled = false,
  aiSearchLoginRequired = false,
  builderMessage,
  error,
  hasAnySelection,
  loading,
  mergeButtonLabel = 'Save/Merge Results',
  searchTableCount,
  showHelp = true,
  title = 'Search Tables',
  onAddAISearchTable,
  onAddSearchTable,
  onMergeResults,
  onDeleteSelectedRows,
  onKeepSelectedRows,
}: PastProjectsActionBarProps) => (
  <div className="project-grid-card past-projects-action-bar">
    <div className="project-grid-card-header">
      <h2 className="project-grid-card-title">{title}</h2>
    </div>

    <div className="past-projects-action-bar-controls">
      <div className="past-projects-action-bar-group" aria-label="Tables and merge">
        <button type="button" className="itg-btn itg-btn-primary" onClick={onAddSearchTable} disabled={loading || Boolean(error)}>
          + Search Table
        </button>
        {onAddAISearchTable ? (
          <button
            type="button"
            className={`itg-btn itg-btn-primary past-projects-ai-table-button${aiSearchLoginRequired ? ' is-login-required' : ''}`}
            aria-disabled={aiSearchLoginRequired || undefined}
            onClick={onAddAISearchTable}
            disabled={loading || Boolean(error) || aiSearchDisabled}
          >
            + AI Search Table
          </button>
        ) : null}
        <button
          type="button"
          className="itg-btn itg-btn-outline"
          onClick={onMergeResults}
          disabled={!searchTableCount || !hasAnySelection}
        >
          {mergeButtonLabel}
        </button>
      </div>
      <div className="past-projects-action-bar-group" aria-label="Selection">
        <button type="button" className="itg-btn itg-btn-outline" onClick={onDeleteSelectedRows} disabled={!hasAnySelection}>
          Delete Selected Rows
        </button>
        <button type="button" className="itg-btn itg-btn-outline" onClick={onKeepSelectedRows} disabled={!hasAnySelection}>
          Keep Selected Rows
        </button>
      </div>
    </div>

    {showHelp ? (
      <details className="past-projects-help-details">
      <summary className="past-projects-help-summary">More help: buttons, merge &amp; tables</summary>
      <p className="past-projects-help-intro">
        The row of buttons above runs the main workflow. Expand this section for a full walkthrough of what each action
        does, how merge combines tables, and how deleting a table differs from deleting rows inside a table.
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
          <strong>+ AI Search Table</strong>
          <span>
            Adds a separate AI search table. Enter an AI query inside that table to load matching past projects, then
            use the same row checkboxes and merge buttons as a regular search table.
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>{mergeButtonLabel}</strong>
          {mergeButtonLabel === 'Save/Merge Results' ? (
            <span>
              Saves the rows you have <em>checked</em> across <strong>every open search table</strong> into{' '}
              <strong>Saved Merged Results</strong> below. Only checked rows are included, so tick the boxes for the
              projects you want first. If the same project is checked in more than one table, it is stored once. This
              button stays disabled until at least one row is selected.
            </span>
          ) : (
            <span>
              Adds the rows you have <em>checked</em> across <strong>every open search table</strong> into this shared
              past project result. Only checked rows are included, so tick the boxes for the projects you want first.
              If the same project is checked in more than one table, it is added once. This button stays disabled until
              at least one row is selected.
            </span>
          )}
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
          <strong>Delete table</strong>
          <span>
            When more than one search table is open, each table shows a trash button in its header. Click it to remove
            that table only. The button is hidden when there is only one table, so the final table stays available.
          </span>
        </div>
        <div className="project-grid-help-card project-grid-help-card--wide">
          <strong>Inside each table</strong>
          <span>
            Use the search field, click column headers to sort, and change <strong>Per page</strong> if you want more
            rows at once. Open <strong>View</strong> on a row to read abstracts and student names when available. Use
            the table toolbar for “Refresh Search Table”, “Undo Row Change”, “Select all entries”, “Deselect”, and
            “Show / Hide all details” for that table only.
          </span>
        </div>
      </div>
      </details>
    ) : null}

    {builderMessage ? <p className="project-grid-status">{builderMessage}</p> : null}
  </div>
);
