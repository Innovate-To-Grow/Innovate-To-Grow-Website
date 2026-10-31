import type {ReactNode} from 'react';
import {softDisabled} from '../../shared/utils/softDisabled';
import type {SearchTableRows} from '../state/useSearchTableRows';
import type {SearchTableSave} from '../state/useSearchTableSave';
import type {SaveOrigin} from '../state/types';

interface SaveControlsProps {
  origin: SaveOrigin;
  save: SearchTableSave;
  hasSelection: boolean;
  selectedCount: number;
  hiddenSelectedCount: number;
  mergeDisabled: boolean;
  mergeLabel: string;
  mergingVerb: string;
  /** Why the button is unavailable while no row is checked (rendered by SearchTableToolbar). */
  selectionHintId: string;
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
  selectionHintId,
}: SaveControlsProps) => (
  <>
    <button
      type="button"
      className="itg-btn itg-btn-primary search-table-save-button"
      onClick={() => save.saveSelected(origin)}
      // aria-disabled, not disabled (saveSelected ignores the press): a save, which unchecks the rows it took, keeps
      // keyboard focus on the button that was pressed.
      aria-disabled={save.isSaving || !hasSelection || mergeDisabled || undefined}
      aria-describedby={hasSelection ? undefined : selectionHintId}
    >
      {/* Each changing text is its element's only child, so page translation cannot leave a stale copy behind. */}
      <span>{save.isSaving ? `${mergingVerb}…` : mergeLabel}</span>
      {!save.isSaving && selectedCount ? (
        <span className="search-table-save-count" aria-hidden="true">{` · ${selectedCount}`}</span>
      ) : null}
    </button>
    {selectedCount ? (
      <span className="search-table-selection-count">
        {`${selectedCount} selected${hiddenSelectedCount ? ` (${hiddenSelectedCount} not shown by the current search)` : ''}`}
      </span>
    ) : null}
  </>
);

interface TidyActionsProps {
  tableRows: SearchTableRows;
  isSaving: boolean;
  selectionHintId: string;
  onRefresh?: () => void;
}

// Removing, keeping and undoing rows can leave their own button with nothing to do, so they stay focusable.
const TidyActions = ({tableRows, isSaving, selectionHintId, onRefresh}: TidyActionsProps) => {
  const {hasSelection} = tableRows.table;
  const selectionHint = hasSelection ? undefined : selectionHintId;
  return (
    <div className="project-grid-toolbar-cluster search-table-action-group" role="group" aria-label="Tidy this table">
      <span className="search-table-group-label" aria-hidden="true">
        Tidy this table
      </span>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        aria-describedby={selectionHint}
        {...softDisabled(!hasSelection || isSaving, tableRows.removeSelected)}
      >
        Remove from Table
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        aria-describedby={selectionHint}
        {...softDisabled(!hasSelection || isSaving, tableRows.keepSelected)}
      >
        Keep Only Selected
      </button>
      <button type="button" className="itg-btn itg-btn-text" {...softDisabled(!tableRows.canUndo || isSaving, tableRows.undo)}>
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
  /** Names the Save group after what its button does ("Add to Curation" in the builder and on a shared page). */
  saveGroupLabel: string;
  /** Id for the hint the selection-dependent buttons point to while no row is checked. */
  selectionHintId: string;
  onRefresh?: () => void;
}

/** The toolbar above the table: Save, selection shortcuts, and the table-tidying actions. */
export const SearchTableToolbar = ({
  tableRows,
  save,
  saveControls,
  topStatus,
  isPhone,
  saveGroupLabel,
  selectionHintId,
  onRefresh,
}: SearchTableToolbarProps) => {
  const {table} = tableRows;
  const tidyActions = (
    <TidyActions tableRows={tableRows} isSaving={save.isSaving} selectionHintId={selectionHintId} onRefresh={onRefresh} />
  );
  return (
    <div className="search-table-actions">
      <span id={selectionHintId} hidden>
        Check one or more rows in the table first.
      </span>
      <div className="search-table-save-row">
        <div className="project-grid-toolbar-cluster search-table-save-group" role="group" aria-label={saveGroupLabel}>
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
            aria-describedby={table.hasSelection ? undefined : selectionHintId}
            {...softDisabled(!table.hasSelection, () => {
              save.clearSaveStatus();
              table.clearSelection();
            })}
          >
            Deselect
          </button>
        </div>
        {isPhone ? (
          // Seven buttons, most of them disabled until rows are checked, would push the results
          // a full screen down on a phone; the table-tidying ones fold away here.
          <details className="search-table-more-actions">
            <summary className="search-table-more-actions-summary">More Table Actions</summary>
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
