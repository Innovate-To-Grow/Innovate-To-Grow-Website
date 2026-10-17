interface PastProjectsActionBarProps {
  aiSearchDisabled?: boolean;
  aiSearchLoginRequired?: boolean;
  builderMessage: string;
  error: string | null;
  loading: boolean;
  showHelp?: boolean;
  title?: string;
  /** How the help text names each table's save button, where it saves to, and the saved-row chip. */
  saveLabel?: string;
  saveTarget?: string;
  savedLabel?: string;
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
  saveLabel = 'Save Selected',
  saveTarget = 'your saved results at the top of the page',
  savedLabel = 'Saved',
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
          <strong>{saveLabel}</strong>
          <span>
            Lives <strong>inside each search table</strong> and adds the rows you have <em>checked</em> in that table to{' '}
            {saveTarget} (projects already there are stored once). Each table saves only its own checked rows, and the
            result is shown right under that table&apos;s buttons. Those projects are then marked{' '}
            <strong>{savedLabel}</strong> in every table.
          </span>
        </div>
        <div className="project-grid-help-card">
          <strong>Remove from Table / Keep Only Selected / Undo Row Change</strong>
          <span>
            These only tidy the search table itself and never save anything. <strong>Remove from Table</strong> removes
            the checked rows from the table; <strong>Keep Only Selected</strong> removes every row that is{' '}
            <em>not</em> checked and keeps the rest checked, ready for {saveLabel}; <strong>Undo Row Change</strong>{' '}
            reverses the last of these in that table.
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
            rows at once. Open <strong>View</strong> on a row to read abstracts and student names when available.{' '}
            <strong>Select All</strong> and the header checkbox select the rows that match the current search, and the
            toolbar shows how many rows are selected. Use “Deselect” to clear the selection and (for full-archive
            tables) “Refresh Search Table” to reload the archive.
          </span>
        </div>
      </div>
      </details>
    ) : null}

    {builderMessage ? <p className="project-grid-status">{builderMessage}</p> : null}
  </div>
);
