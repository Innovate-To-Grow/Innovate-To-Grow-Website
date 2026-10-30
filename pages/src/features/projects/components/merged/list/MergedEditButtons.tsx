import {PastProjectsDialog} from '../../builder/dialog/PastProjectsDialog';
import {softDisabled} from '../../shared/utils/softDisabled';

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

/**
 * The "Edit list" toolbar group; renders nothing when no edit applies. Each of its buttons can leave itself with
 * nothing to do, so they stay focusable while unavailable (see softDisabled).
 */
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
          {...softDisabled(!bulkRemove.hasSelection || isSharing, bulkRemove.onRemove)}
        >
          Remove Selected
        </button>
      ) : null}
      {undo ? (
        <button type="button" className="itg-btn itg-btn-text" {...softDisabled(!undo.canUndo || isSharing, undo.onUndo)}>
          Undo
        </button>
      ) : null}
      {canReset ? (
        <button
          type="button"
          className="itg-btn itg-btn-text itg-btn-danger"
          {...softDisabled(!hasRows || isSharing, () => onRequestBulkAction('reset-builder'))}
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
          {...softDisabled(!shared.canUndo || shared.isSaving, () => void shared.onUndo())}
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
