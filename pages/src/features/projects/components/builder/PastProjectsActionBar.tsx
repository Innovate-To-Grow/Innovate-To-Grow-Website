interface PastProjectsActionBarProps {
  aiSearchDisabled?: boolean;
  aiSearchLoginRequired?: boolean;
  builderMessage: string;
  error: string | null;
  loading: boolean;
  showHelp?: boolean;
  title?: string;
  onAddAISearchTable?: () => void;
  onAddSearchTable: () => void;
}

export const PastProjectsActionBar = ({
  aiSearchDisabled = false,
  aiSearchLoginRequired = false,
  builderMessage,
  error,
  loading,
  showHelp = true,
  title = 'Search Tables',
  onAddAISearchTable,
  onAddSearchTable,
}: PastProjectsActionBarProps) => (
  <div className="project-grid-card past-projects-action-bar">
    <div className="project-grid-card-header">
      <h2 className="project-grid-card-title">{title}</h2>
    </div>

    <div className="past-projects-action-bar-controls">
      <div className="past-projects-action-bar-group" aria-label="Tables">
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
      </div>
    </div>

    {showHelp ? (
      <details className="past-projects-help-details">
      <summary className="past-projects-help-summary">More help: buttons, saving &amp; tables</summary>
      <p className="past-projects-help-intro">
        Add one or more search tables, then work inside each table to choose the projects you want. Expand this section
        for a full walkthrough of what each action does and how saving combines tables.
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
            use the same row checkboxes and per-table buttons as a regular search table.
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>Save Selected / Delete Selected / Keep Selected</strong>
          <span>
            These live <strong>inside each search table</strong> and act on the rows you have <em>checked</em> in that
            table. <strong>Save Selected</strong> adds the checked rows to your saved results below (duplicates are
            stored once); <strong>Delete Selected</strong> removes the checked rows; <strong>Keep Selected</strong>{' '}
            removes every row that is <em>not</em> checked. They stay disabled until you check at least one row.
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>Undo Row Change</strong>
          <span>
            Inside a table, reverses the last <strong>Delete Selected</strong> or <strong>Keep Selected</strong> in that
            table. It is greyed out until you make such a change, then becomes available to restore the rows.
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
            the table toolbar for “Save Selected”, “Delete Selected”, “Keep Selected”, “Undo Row Change”, “Select All
            Entries”, “Deselect”, and (for full-archive tables) “Refresh Search Table”.
          </span>
        </div>
      </div>
      </details>
    ) : null}

    {builderMessage ? <p className="project-grid-status">{builderMessage}</p> : null}
  </div>
);
