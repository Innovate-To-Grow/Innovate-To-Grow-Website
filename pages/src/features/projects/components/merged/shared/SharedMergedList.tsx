import {RichDetailPreview} from '../../richText/content/RichDetailPreview';
import type {ProjectGridItem, ProjectGridRow} from '../../grid/contracts/projectGrid';
import {curationBranding} from '../list/curationBranding';
import {noteHasContent, sharedListExportTarget} from '../list/curationNote';
import {MergedEditButtons} from '../list/MergedEditButtons';
import {MergedExportGroup} from '../list/MergedExportGroup';
import {MergedListGrid} from '../list/MergedListGrid';
import {SharedListHeader} from '../list/MergedListHeader';
import {SharedLinkPanel} from './SharedLinkPanel';
import {SharedNoteEditor} from './SharedNoteEditor';
import {useMergedList} from '../list/useMergedList';
import {useNoteInsertFields} from '../list/useNoteInsertFields';
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
        sharedListExportTarget(
          title,
          {enabled: canEdit, titleDraft: editor.titleDraft, noteDraft: editor.noteDraft, savedNoteHtml: noteHtml},
          allRows,
        )
      }
      onStatus={setStatusMessage}
    />
  );

  return (
    <section
      id={id}
      className={`project-grid-shared-list${className ? ` ${className}` : ''}`}
      aria-labelledby={isEditingTitle ? undefined : headingId}
      aria-label={isEditingTitle ? 'Curation' : undefined}
    >
      <SharedListHeader
        headingId={headingId}
        eyebrow={curationBranding(allRows).eyebrow}
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
        title={title}
        rows={rows}
        sharedMode
        onDeleteRow={
          canEdit
            ? (row) => {
                list.rememberRemoval(row);
                void editor.deleteRow(row);
              }
            : undefined
        }
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

      {/* Always in the page, so screen readers announce its first message too. */}
      <p className="project-grid-status" role="status">
        {list.statusMessage}
      </p>
    </section>
  );
};
