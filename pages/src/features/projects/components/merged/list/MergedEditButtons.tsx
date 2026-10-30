import {PastProjectsDialog} from '../../builder/dialog/PastProjectsDialog';

export type PendingBulkAction = 'reset-builder';

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
          Undo
        </button>
      ) : null}
      {canReset ? (
        <button
          type="button"
          className="itg-btn itg-btn-text itg-btn-danger"
          onClick={() => onRequestBulkAction('reset-builder')}
          disabled={!hasRows || isSharing}
        >
          Clear Draft
        </button>
      ) : null}
      {/* A curation keeps at least one project (the API refuses an empty one), so it has no "remove all";
          deleting a whole curation is done from My Curations. */}
      {shared ? (
        <button
          type="button"
          className="itg-btn itg-btn-text"
          onClick={() => void shared.onUndo()}
          disabled={!shared.canUndo || shared.isSaving}
        >
          Undo
        </button>
      ) : null}
    </div>
  );
};

interface BulkActionDialogProps {
  onCancel: () => void;
  onConfirm: () => void;
}

/** Confirms clearing the builder's draft. */
export const BulkActionDialog = ({onCancel, onConfirm}: BulkActionDialogProps) => (
  <PastProjectsDialog
    title="Clear the curation draft?"
    confirmLabel="Clear Draft"
    destructive
    onCancel={onCancel}
    onConfirm={onConfirm}
  >
    <p>Remove every project from the curation draft? You can undo this right afterward.</p>
  </PastProjectsDialog>
);
