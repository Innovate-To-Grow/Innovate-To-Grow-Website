import {PastProjectsDialog} from '../builder/PastProjectsDialog';

export type PendingBulkAction = 'reset-builder' | 'remove-all-shared';

interface MergedEditButtonsProps {
  /** Builder: check rows, then "Remove Selected". */
  bulkRemove: {hasSelection: boolean; onRemove: () => void} | null;
  /** Builder: step back through merged-row changes. */
  undo: {canUndo: boolean; onUndo: () => void} | null;
  /** Builder: clear every merged row (after a confirmation dialog). */
  canReset: boolean;
  /** Shared page the viewer may edit. */
  shared: {canUndo: boolean; isSaving: boolean; onUndo: () => void} | null;
  hasRows: boolean;
  /** A curation is being saved from the rows as they were at the click. */
  isSharing: boolean;
  onRequestBulkAction: (action: PendingBulkAction) => void;
}

/** The "Edit list" toolbar group; renders nothing when no edit applies. */
export const MergedEditButtons = ({
  bulkRemove,
  undo,
  canReset,
  shared,
  hasRows,
  isSharing,
  onRequestBulkAction,
}: MergedEditButtonsProps) => {
  if (!undo && !canReset && !shared && !bulkRemove) {
    return null;
  }
  return (
    <div className="project-grid-toolbar-cluster project-grid-edit-group" role="group" aria-label="Edit list">
      {bulkRemove ? (
        <button
          type="button"
          className="itg-btn itg-btn-text"
          onClick={bulkRemove.onRemove}
          disabled={!bulkRemove.hasSelection || isSharing}
        >
          Remove Selected
        </button>
      ) : null}
      {undo ? (
        <button type="button" className="itg-btn itg-btn-text" onClick={undo.onUndo} disabled={!undo.canUndo || isSharing}>
          Undo Merged Change
        </button>
      ) : null}
      {canReset ? (
        <button
          type="button"
          className="itg-btn itg-btn-text itg-btn-danger"
          onClick={() => onRequestBulkAction('reset-builder')}
          disabled={!hasRows || isSharing}
        >
          Reset Merged Results
        </button>
      ) : null}
      {shared ? (
        <>
          <button
            type="button"
            className="itg-btn itg-btn-text"
            onClick={() => void shared.onUndo()}
            disabled={!shared.canUndo || shared.isSaving}
          >
            Undo Shared Change
          </button>
          <button
            type="button"
            className="itg-btn itg-btn-text itg-btn-danger"
            onClick={() => onRequestBulkAction('remove-all-shared')}
            disabled={shared.isSaving}
          >
            Remove All
          </button>
        </>
      ) : null}
    </div>
  );
};

interface BulkActionDialogProps {
  action: PendingBulkAction;
  onCancel: () => void;
  onConfirm: () => void;
}

export const BulkActionDialog = ({action, onCancel, onConfirm}: BulkActionDialogProps) => {
  const isReset = action === 'reset-builder';
  return (
    <PastProjectsDialog
      title={isReset ? 'Reset merged results?' : 'Remove all projects?'}
      confirmLabel={isReset ? 'Reset Merged Results' : 'Close'}
      showCancel={isReset}
      onCancel={onCancel}
      onConfirm={onConfirm}
    >
      {isReset ? (
        <p>Clear every project from the saved merged results? You can undo this immediately afterward.</p>
      ) : (
        <p>
          This shared page cannot be saved with zero projects because the API requires at least one row. Remove
          rows individually, or delete the shared page if it is no longer needed.
        </p>
      )}
    </PastProjectsDialog>
  );
};
