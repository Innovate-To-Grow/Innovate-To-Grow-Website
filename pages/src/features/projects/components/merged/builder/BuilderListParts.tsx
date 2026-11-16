import {type ReactNode} from 'react';
import {builderExportTarget, type SignInToSave} from '../list/curationNote';
import {CurationSaveSection} from './CurationSaveSection';
import {BulkActionDialog, MergedEditButtons} from '../list/MergedEditButtons';
import {MergedExportGroup} from '../list/MergedExportGroup';
import {useCurationShare} from './useCurationShare';
import {useMergedList} from '../list/useMergedList';
import {useNoteInsertFields} from '../list/useNoteInsertFields';
import {type BuilderMergedListProps} from './useBuilderList';

interface BuilderListToolbarProps
  extends Pick<BuilderMergedListProps, 'rows' | 'title' | 'onDeleteRows' | 'canUndoRows' | 'onUndoRows' | 'onResetRows'> {
  list: ReturnType<typeof useMergedList>;
  canShare: boolean;
  curation: ReturnType<typeof useCurationShare>;
}

/** Exports of the shown rows, and removing / undoing / resetting rows. */
export const BuilderListToolbar = ({
  list,
  rows,
  title,
  canShare,
  curation,
  onDeleteRows,
  canUndoRows,
  onUndoRows,
  onResetRows,
}: BuilderListToolbarProps) => {
  const {table, visibleRows, setStatusMessage} = list;
  const {isSharing} = curation;
  // Rows checked under an earlier search stay checked when the search changes. Removing acts only on the
  // checked rows the search shows, like saving and exports; the hidden ones stay checked.
  const shownSelectedRows = table.filteredRows.filter((row) => table.selectedKeys.has(row.__key));

  const handleRemoveSelectedRows = () => {
    if (!onDeleteRows || !shownSelectedRows.length || isSharing) {
      return;
    }
    onDeleteRows(shownSelectedRows);
    table.removeFromSelection(shownSelectedRows.map((row) => row.__key));
  };

  return (
    <div className="project-grid-inline-actions">
      <MergedExportGroup
        rows={visibleRows}
        buildTarget={() =>
          builderExportTarget(
            title,
            {enabled: canShare, nameDraft: curation.nameDraft, noteDraft: curation.noteDraft},
            visibleRows,
          )
        }
        onStatus={setStatusMessage}
        reloadNote="Your curation draft is kept."
      />
      <MergedEditButtons
        bulkRemove={onDeleteRows ? {hasSelection: shownSelectedRows.length > 0, onRemove: handleRemoveSelectedRows} : null}
        undo={onUndoRows ? {canUndo: canUndoRows, onUndo: onUndoRows} : null}
        canReset={Boolean(onResetRows)}
        shared={null}
        hasRows={rows.length > 0}
        isSharing={isSharing}
        onRequestBulkAction={list.setPendingBulkAction}
      />
    </div>
  );
};

interface BuilderListFooterProps {
  list: ReturnType<typeof useMergedList>;
  curation: ReturnType<typeof useCurationShare>;
  isAuthenticated: boolean;
  showSaveSection: boolean;
  noteInsert: ReturnType<typeof useNoteInsertFields>;
  saveButton: ReactNode;
  pendingSaveCount: number;
  signIn: SignInToSave;
  onConfirmBulkAction: () => void;
}

/** Under the table and its status line: the curation's name and note with its save button, and the bulk-action dialog. */
export const BuilderListFooter = ({
  list,
  curation,
  isAuthenticated,
  showSaveSection,
  noteInsert,
  saveButton,
  pendingSaveCount,
  signIn,
  onConfirmBulkAction,
}: BuilderListFooterProps) => (
  <>
    {showSaveSection ? (
      <CurationSaveSection
        isAuthenticated={isAuthenticated}
        rows={list.visibleRows}
        nameDraft={curation.nameDraft}
        noteDraft={curation.noteDraft}
        onNameDraftChange={curation.setNameDraft}
        onNoteDraftChange={curation.setNoteDraft}
        noteInsert={noteInsert}
        saveButton={saveButton}
        pendingSaveCount={pendingSaveCount}
        signIn={signIn}
      />
    ) : null}

    {list.pendingBulkAction ? (
      <BulkActionDialog onCancel={() => list.setPendingBulkAction(null)} onConfirm={onConfirmBulkAction} />
    ) : null}
  </>
);
