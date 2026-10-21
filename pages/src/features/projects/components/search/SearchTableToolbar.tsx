import type {ReactNode} from 'react';
import type {SearchTableRows} from './useSearchTableRows';
import type {SearchTableSave} from './useSearchTableSave';
import type {SaveOrigin} from './types';

interface SaveControlsProps {
  origin: SaveOrigin;
  save: SearchTableSave;
  hasSelection: boolean;
  selectedCount: number;
  hiddenSelectedCount: number;
  mergeDisabled: boolean;
  mergeLabel: string;
  mergingVerb: string;
}

/** A Save button with the selection count beside it (shown above the table, and under long pages). */
export const SaveControls = ({
  origin,
  save,
  hasSelection,
  selectedCount,
  hiddenSelectedCount,
  mergeDisabled,
  mergeLabel,
  mergingVerb,
}: SaveControlsProps) => (
  <>
    <button
      type="button"
      className="itg-btn itg-btn-primary search-table-save-button"
      onClick={() => save.saveSelected(origin)}
      // aria-disabled (not disabled) while saving keeps keyboard focus on the button that was pressed.
      disabled={!save.isSaving && (!hasSelection || mergeDisabled)}
      aria-disabled={save.isSaving || undefined}
    >
      {save.isSaving ? `${mergingVerb}…` : mergeLabel}
      {!save.isSaving && selectedCount ? (
        <span className="search-table-save-count" aria-hidden="true">
          {' '}
          · {selectedCount}
        </span>
      ) : null}
    </button>
    {selectedCount ? (
      <span className="search-table-selection-count">
        {selectedCount} selected
        {hiddenSelectedCount ? ` (${hiddenSelectedCount} not shown by the current search)` : ''}
      </span>
    ) : null}
  </>
);

interface TidyActionsProps {
  tableRows: SearchTableRows;
  isSaving: boolean;
  onRefresh?: () => void;
}

const TidyActions = ({tableRows, isSaving, onRefresh}: TidyActionsProps) => {
  const {hasSelection} = tableRows.table;
  return (
    <div className="project-grid-toolbar-cluster search-table-action-group" role="group" aria-label="Tidy this table">
      <span className="search-table-group-label" aria-hidden="true">
        Tidy this table
      </span>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        onClick={tableRows.removeSelected}
        disabled={!hasSelection || isSaving}
      >
        Remove from Table
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        onClick={tableRows.keepSelected}
        disabled={!hasSelection || isSaving}
      >
        Keep Only Selected
      </button>
      <button type="button" className="itg-btn itg-btn-text" onClick={tableRows.undo} disabled={!tableRows.canUndo || isSaving}>
        Undo Row Change
      </button>
      {onRefresh ? (
        <button type="button" className="itg-btn itg-btn-text" onClick={onRefresh} disabled={isSaving}>
          Refresh Search Table
        </button>
      ) : null}
    </div>
  );
};

interface SearchTableToolbarProps {
  tableRows: SearchTableRows;
  save: SearchTableSave;
  saveControls: ReactNode;
  topStatus: ReactNode;
  isPhone: boolean;
  onRefresh?: () => void;
}

/** The toolbar above the table: Save, selection shortcuts, and the table-tidying actions. */
export const SearchTableToolbar = ({tableRows, save, saveControls, topStatus, isPhone, onRefresh}: SearchTableToolbarProps) => {
  const {table} = tableRows;
  const tidyActions = <TidyActions tableRows={tableRows} isSaving={save.isSaving} onRefresh={onRefresh} />;
  return (
    <div className="search-table-actions">
      <div className="search-table-save-row">
        <div className="project-grid-toolbar-cluster search-table-save-group" role="group" aria-label="Save">
          {saveControls}
        </div>
        {topStatus}
      </div>
      <div className="search-table-secondary-actions">
        <div className="project-grid-toolbar-cluster search-table-action-group" role="group" aria-label="Selection">
          <span className="search-table-group-label" aria-hidden="true">
            Selection
          </span>
          <button
            type="button"
            className="itg-btn itg-btn-text"
            onClick={() => {
              save.clearSaveStatus();
              table.addToSelection(table.filteredRows);
            }}
            disabled={!table.filteredRows.length}
          >
            Select All
          </button>
          <button
            type="button"
            className="itg-btn itg-btn-text"
            onClick={() => {
              save.clearSaveStatus();
              table.clearSelection();
            }}
            disabled={!table.hasSelection}
          >
            Deselect
          </button>
        </div>
        {isPhone ? (
          // Seven buttons, most of them disabled until rows are checked, would push the results
          // a full screen down on a phone; the table-tidying ones fold away here.
          <details className="search-table-more-actions">
            <summary className="search-table-more-actions-summary">More table actions</summary>
            {tidyActions}
          </details>
        ) : (
          <>
            <span className="search-table-group-divider" aria-hidden="true" />
            {tidyActions}
          </>
        )}
      </div>
    </div>
  );
};
