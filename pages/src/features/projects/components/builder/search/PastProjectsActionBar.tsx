import {useId} from 'react';

interface PastProjectsActionBarProps {
  aiSearchDisabled?: boolean;
  aiSearchLoginRequired?: boolean;
  builderMessage: string;
  error: string | null;
  loading: boolean;
  showHelp?: boolean;
  title?: string;
  /** Id for the heading, so the section holding the tables can be labelled by it. */
  headingId?: string;
  /** How the help text names each table's save button, where it saves to, and the saved-row tag. */
  saveLabel?: string;
  saveTarget?: string;
  savedLabel?: string;
  onAddAISearchTable?: () => void;
  onAddSearchTable: () => void;
}

function LockIcon() {
  return (
    <svg
      className="past-projects-lock-icon"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="5" y="11" width="14" height="10" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

interface AISearchTableButtonProps {
  loginRequired: boolean;
  disabled: boolean;
  loginNoteId: string;
  onClick: () => void;
}

/** "+ AI Search Table", or a locked button pointing at the sign-in note. */
const AISearchTableButton = ({loginRequired, disabled, loginNoteId, onClick}: AISearchTableButtonProps) => (
  <button
    type="button"
    className={`itg-btn itg-btn-primary past-projects-ai-table-button${
      loginRequired ? ' is-login-required' : ''
    }`}
    onClick={onClick}
    disabled={disabled}
    aria-describedby={loginRequired ? loginNoteId : undefined}
  >
    {loginRequired ? (
      <>
        <LockIcon />
        AI Search Table
      </>
    ) : (
      '+ AI Search Table'
    )}
  </button>
);

type HelpProps = Required<Pick<PastProjectsActionBarProps, 'saveLabel' | 'saveTarget' | 'savedLabel'>>;

/** What each button does, folded away under a summary. */
const PastProjectsHelp = ({saveLabel, saveTarget, savedLabel}: HelpProps) => (
  <details className="past-projects-help-details">
    <summary className="past-projects-help-summary">Help: buttons, saving and tables</summary>
    <p className="past-projects-help-intro">
      Add one or more search tables, then work inside each table to choose the projects you want.
    </p>
    <dl className="past-projects-help-grid">
      <div className="project-grid-help-card">
        <dt>+ Search Table</dt>
        <dd>
          Adds another search table. Each table loads the full past-project archive on its own, so you can try
          different searches side by side (for example, one for a class code and another for an organization).
        </dd>
      </div>
      <div className="project-grid-help-card">
        <dt>+ AI Search Table</dt>
        <dd>
          Adds a separate AI search table (sign-in required). Describe what you are looking for inside that table to
          load matching past projects, then use the same checkboxes and buttons as a regular search table.
        </dd>
      </div>
      <div className="project-grid-help-card">
        <dt>{saveLabel}</dt>
        <dd>
          Lives inside each search table and adds the rows you have checked in that table to {saveTarget}{' '}
          (projects already there are stored once). The result is shown right next to the button, and those
          projects are then tagged <strong>{savedLabel}</strong> in every table.
        </dd>
      </div>
      <div className="project-grid-help-card">
        <dt>Tidy this table</dt>
        <dd>
          <strong>Remove from Table</strong> drops the checked rows; <strong>Keep Only Selected</strong> drops
          every row that is not checked and keeps the rest checked, ready for {saveLabel};{' '}
          <strong>Undo Row Change</strong> reverses the last of these. They never save anything.
        </dd>
      </div>
      <div className="project-grid-help-card">
        <dt>Delete table</dt>
        <dd>
          When more than one search table is open, each one has a Delete table button in its header. It removes
          that table only, so the last table always stays.
        </dd>
      </div>
      <div className="project-grid-help-card project-grid-help-card--wide">
        <dt>Inside each table</dt>
        <dd>
          Search, click a column heading to sort, and change <strong>Per page</strong> to see more rows at once.
          Open <strong>Details</strong> on a row to read its abstract and team members.{' '}
          <strong>Select All</strong> and the header checkbox select the rows that match the current search, and
          the table shows how many rows are selected. <strong>Deselect</strong> clears the selection and{' '}
          <strong>Refresh Search Table</strong> reloads the archive.
        </dd>
      </div>
    </dl>
  </details>
);

/** Header of the "Search Tables" section: its title, the add-table buttons and the help. */
export const PastProjectsActionBar = ({
  aiSearchDisabled = false,
  aiSearchLoginRequired = false,
  builderMessage,
  error,
  loading,
  showHelp = true,
  title = 'Search Tables',
  headingId,
  saveLabel = 'Save Selected',
  saveTarget = 'your saved results at the top of the page',
  savedLabel = 'Saved',
  onAddAISearchTable,
  onAddSearchTable,
}: PastProjectsActionBarProps) => {
  const loginNoteId = useId();
  const tablesUnavailable = loading || Boolean(error);

  return (
    <div className="past-projects-action-bar">
      <div className="past-projects-action-bar-header">
        <h2 id={headingId} className="project-grid-card-title past-projects-action-bar-title">
          {title}
        </h2>
        <div className="past-projects-action-bar-group" role="group" aria-label="Add a table">
          {/* Filled navy, like the reference's "+ Search Table" and "Click Here to Submit Your Project". */}
          <button
            type="button"
            className="itg-btn itg-btn-primary"
            onClick={onAddSearchTable}
            disabled={tablesUnavailable}
          >
            + Search Table
          </button>
          {onAddAISearchTable ? (
            <AISearchTableButton
              loginRequired={aiSearchLoginRequired}
              disabled={tablesUnavailable || aiSearchDisabled}
              loginNoteId={loginNoteId}
              onClick={onAddAISearchTable}
            />
          ) : null}
        </div>
      </div>

      {onAddAISearchTable && aiSearchLoginRequired ? (
        <p id={loginNoteId} className="past-projects-action-bar-note">
          AI Search Table needs you to sign in.
        </p>
      ) : null}

      {showHelp ? <PastProjectsHelp saveLabel={saveLabel} saveTarget={saveTarget} savedLabel={savedLabel} /> : null}

      {builderMessage ? <p className="project-grid-status past-projects-builder-message">{builderMessage}</p> : null}
    </div>
  );
};
