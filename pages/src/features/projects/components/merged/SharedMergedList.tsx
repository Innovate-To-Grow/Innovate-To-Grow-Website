import {RichDetailPreview} from '../richText/RichDetailPreview';
import type {ProjectGridItem, ProjectGridRow} from '../projectGrid';
import {noteHasContent, sharedListExportTarget} from './curationNote';
import {BulkActionDialog, MergedEditButtons} from './MergedEditButtons';
import {MergedExportGroup} from './MergedExportGroup';
import {MergedListGrid} from './MergedListGrid';
import {SharedListHeader} from './MergedListHeader';
import {SharedLinkPanel} from './SharedLinkPanel';
import {SharedNoteEditor} from './SharedNoteEditor';
import {useMergedList} from './useMergedList';
import {useNoteInsertFields} from './useNoteInsertFields';
import {useSharedListEditor} from './useSharedListEditor';

export interface SharedMergedListProps {
  id?: string;
  className?: string;
  rows: ProjectGridItem[];
  title: string;
  note?: string;
  sharedAt?: string;
  /** The viewer owns the list: rename, edit the note, remove rows. Needs `onUpdateShare`. */
  editable: boolean;
  onUpdateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  canUndoRows: boolean;
  onUndoRows?: () => void;
}

/** The saved note, read-only, for viewers who cannot edit it. */
const SharedNoteView = ({noteHtml}: {noteHtml: string}) =>
  noteHasContent(noteHtml) ? (
    <div className="project-grid-shared-note">
      <p className="project-grid-shared-note-label">Curation note</p>
      <RichDetailPreview className="project-grid-shared-detail-text itg-content" html={noteHtml} />
    </div>
  ) : null;

/** A shared list keeps at least one project, so confirming "remove all" only explains that. */
const SharedBulkActionDialog = ({list}: {list: ReturnType<typeof useMergedList>}) => {
  if (!list.pendingBulkAction) return null;
  const handleConfirm = () => {
    if (list.pendingBulkAction === 'remove-all-shared') {
      list.setStatusMessage(
        'A shared page needs at least one project. Remove rows individually, or delete the shared page if it is no longer needed.',
      );
    }
    list.setPendingBulkAction(null);
  };
  return (
    <BulkActionDialog
      action={list.pendingBulkAction}
      onCancel={() => list.setPendingBulkAction(null)}
      onConfirm={handleConfirm}
    />
  );
};

/** A saved curation's page: its link, note and projects, editable in place by its owner. */
export const SharedMergedList = ({
  id,
  className,
  rows,
  title,
  note,
  sharedAt,
  editable,
  onUpdateShare,
  canUndoRows,
  onUndoRows,
}: SharedMergedListProps) => {
  const canEdit = editable && Boolean(onUpdateShare);
  const list = useMergedList(rows, true);
  const {table, allRows, headingId, setStatusMessage} = list;
  const noteInsert = useNoteInsertFields();
  const {titleInputRef, ...editor} = useSharedListEditor({
    rows,
    allRows,
    title,
    note,
    onUpdateShare,
    onStatus: setStatusMessage,
  });
  const noteHtml = note ?? '';
  // The shareable URL is just the current page URL — derived, not mirrored into state via an effect.
  const shareUrl = window.location.href;
  const isEditingTitle = editor.isEditingTitle;

  // The export represents the whole shared snapshot, so a viewer's transient table search must not narrow it.
  const exportGroup = (
    <MergedExportGroup
      rows={allRows}
      buildTarget={() =>
        sharedListExportTarget(title, {
          enabled: canEdit,
          titleDraft: editor.titleDraft,
          noteDraft: editor.noteDraft,
          savedNoteHtml: noteHtml,
        })
      }
      onError={setStatusMessage}
    />
  );

  return (
    <section
      id={id}
      className={`project-grid-shared-list${className ? ` ${className}` : ''}`}
      aria-labelledby={isEditingTitle ? undefined : headingId}
      aria-label={isEditingTitle ? 'Shared list' : undefined}
    >
      <SharedListHeader
        headingId={headingId}
        title={title}
        rowCount={rows.length}
        sharedAt={sharedAt}
        editor={canEdit ? editor : null}
        titleInputRef={titleInputRef}
      />

      {shareUrl ? (
        <SharedLinkPanel shareUrl={shareUrl} onStatus={setStatusMessage}>
          {exportGroup}
        </SharedLinkPanel>
      ) : null}

      {canEdit ? (
        <SharedNoteEditor editor={editor} rows={allRows} noteInsert={noteInsert} />
      ) : (
        <SharedNoteView noteHtml={noteHtml} />
      )}

      <MergedListGrid
        table={table}
        rows={rows}
        sharedMode
        onDeleteRow={canEdit ? editor.deleteRow : undefined}
        deleteDisabled={false}
        selectable={false}
        toolbar={
          <MergedEditButtons
            bulkRemove={null}
            undo={onUndoRows ? {canUndo: canUndoRows, onUndo: onUndoRows} : null}
            canReset={false}
            shared={canEdit ? {canUndo: editor.canUndo, isSaving: editor.isSaving, onUndo: editor.undoRows} : null}
            hasRows={rows.length > 0}
            isSharing={false}
            onRequestBulkAction={list.setPendingBulkAction}
          />
        }
      />

      <SharedBulkActionDialog list={list} />

      {list.statusMessage ? (
        <p className="project-grid-status" role="status">
          {list.statusMessage}
        </p>
      ) : null}
    </section>
  );
};
