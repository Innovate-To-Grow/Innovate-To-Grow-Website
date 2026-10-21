import type {ReactNode} from 'react';
import {useAuth} from '@/features/auth';
import type {ProjectGridItem, ProjectGridRow} from '../projectGrid';
import {builderExportTarget} from './curationNote';
import {CurationSaveButton, CurationSaveSection} from './CurationSaveSection';
import {BulkActionDialog, MergedEditButtons} from './MergedEditButtons';
import {MergedExportGroup} from './MergedExportGroup';
import {MergedListGrid, NarrowedSearchHint} from './MergedListGrid';
import {BuilderCardHeader} from './MergedListHeader';
import {useCurationShare, type PastProjectShareCreationResult} from './useCurationShare';
import {useMergedList, useRevealRecentlyAdded} from './useMergedList';
import {useNoteInsertFields} from './useNoteInsertFields';

export interface BuilderMergedListProps {
  id?: string;
  className?: string;
  rows: ProjectGridItem[];
  recentlyAdded: {keys: ReadonlySet<string>; token: number} | null;
  pendingSaveCount: number;
  title: string;
  onCreateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<PastProjectShareCreationResult>;
  nameDraft?: string;
  noteDraft?: string;
  onNameDraftChange?: (name: string) => void;
  onNoteDraftChange?: (note: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  onDeleteRows?: (rows: ProjectGridItem[]) => void;
  canUndoRows: boolean;
  onUndoRows?: () => void;
  onResetRows?: () => void;
}

interface BuilderListToolbarProps
  extends Pick<BuilderMergedListProps, 'rows' | 'title' | 'onDeleteRows' | 'canUndoRows' | 'onUndoRows' | 'onResetRows'> {
  list: ReturnType<typeof useMergedList>;
  canShare: boolean;
  curation: ReturnType<typeof useCurationShare>;
}

/** Exports of the shown rows, and removing / undoing / resetting rows. */
const BuilderListToolbar = ({
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

  const handleRemoveSelectedRows = () => {
    if (!onDeleteRows || !table.hasSelection || isSharing) {
      return;
    }
    onDeleteRows(table.selectedRows);
    table.clearSelection();
  };

  return (
    <div className="project-grid-inline-actions">
      <MergedExportGroup
        rows={visibleRows}
        buildTarget={() =>
          builderExportTarget(title, {
            enabled: canShare,
            nameDraft: curation.nameDraft,
            noteDraft: curation.noteDraft,
          })
        }
        onError={setStatusMessage}
      />
      <MergedEditButtons
        bulkRemove={onDeleteRows ? {hasSelection: table.hasSelection, onRemove: handleRemoveSelectedRows} : null}
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

type BuilderListOptions = Pick<
  BuilderMergedListProps,
  | 'rows'
  | 'recentlyAdded'
  | 'pendingSaveCount'
  | 'onCreateShare'
  | 'nameDraft'
  | 'noteDraft'
  | 'onNameDraftChange'
  | 'onNoteDraftChange'
  | 'onDeleteRow'
  | 'onResetRows'
>;

/** The list's table, the curation save, and the row actions, which all wait while a curation is saved. */
function useBuilderList({
  rows,
  recentlyAdded,
  pendingSaveCount,
  onCreateShare,
  nameDraft,
  noteDraft,
  onNameDraftChange,
  onNoteDraftChange,
  onDeleteRow,
  onResetRows,
}: BuilderListOptions) {
  const {isAuthenticated} = useAuth();
  const canShare = Boolean(onCreateShare) && isAuthenticated;
  const list = useMergedList(rows, false);
  const {table, visibleRows, setStatusMessage} = list;
  const noteInsert = useNoteInsertFields();
  const hiddenAddedCount = useRevealRecentlyAdded(table, rows, recentlyAdded);
  const curation = useCurationShare({
    onCreateShare,
    visibleRows,
    pendingSaveCount,
    nameDraft,
    noteDraft,
    onNameDraftChange,
    onNoteDraftChange,
    onStatus: setStatusMessage,
  });
  const {isSharing} = curation;

  const handleDeleteRow = async (row: ProjectGridItem) => {
    if (!onDeleteRow || isSharing) {
      return;
    }
    onDeleteRow(row);
  };

  const handleConfirmBulkAction = () => {
    if (list.pendingBulkAction === 'reset-builder' && !isSharing) {
      onResetRows?.();
    }
    list.setPendingBulkAction(null);
  };

  return {isAuthenticated, canShare, list, noteInsert, hiddenAddedCount, curation, handleDeleteRow, handleConfirmBulkAction};
}

interface BuilderListFooterProps {
  list: ReturnType<typeof useMergedList>;
  curation: ReturnType<typeof useCurationShare>;
  isAuthenticated: boolean;
  showSaveSection: boolean;
  noteInsert: ReturnType<typeof useNoteInsertFields>;
  saveButton: ReactNode;
  pendingSaveCount: number;
  onConfirmBulkAction: () => void;
}

/** Under the table: the curation's name and note with its save button, the bulk-action dialog, and the status. */
const BuilderListFooter = ({
  list,
  curation,
  isAuthenticated,
  showSaveSection,
  noteInsert,
  saveButton,
  pendingSaveCount,
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
      />
    ) : null}

    {list.pendingBulkAction ? (
      <BulkActionDialog
        action={list.pendingBulkAction}
        onCancel={() => list.setPendingBulkAction(null)}
        onConfirm={onConfirmBulkAction}
      />
    ) : null}

    {list.statusMessage ? (
      <p className="project-grid-status" role="status">
        {list.statusMessage}
      </p>
    ) : null}
  </>
);

/**
 * The builder's unsaved merged list. Saving, exports and bulk removal act on the rows the search
 * shows; while a curation is being saved the rows stay as they were at the click.
 */
export const BuilderMergedList = ({
  id,
  className,
  rows,
  recentlyAdded,
  pendingSaveCount,
  title,
  onCreateShare,
  nameDraft,
  noteDraft,
  onNameDraftChange,
  onNoteDraftChange,
  onDeleteRow,
  onDeleteRows,
  canUndoRows,
  onUndoRows,
  onResetRows,
}: BuilderMergedListProps) => {
  const {isAuthenticated, canShare, list, noteInsert, hiddenAddedCount, curation, handleDeleteRow, handleConfirmBulkAction} =
    useBuilderList({
      rows,
      recentlyAdded,
      pendingSaveCount,
      onCreateShare,
      nameDraft,
      noteDraft,
      onNameDraftChange,
      onNoteDraftChange,
      onDeleteRow,
      onResetRows,
    });
  const {table, visibleRows, headingId} = list;
  const {isSharing} = curation;
  const shownCount = table.filteredRows.length;

  const saveButton = canShare ? (
    <CurationSaveButton
      hasRows={visibleRows.length > 0}
      isSharing={isSharing}
      pendingSaveCount={pendingSaveCount}
      onSave={() => void curation.createShare()}
    />
  ) : null;

  return (
    <section
      id={id}
      className={`itg-panel project-grid-card project-grid-merged${className ? ` ${className}` : ''}`}
      aria-labelledby={headingId}
    >
      <BuilderCardHeader
        headingId={headingId}
        title={title}
        rowCount={rows.length}
        canSave={Boolean(onCreateShare)}
        isAuthenticated={isAuthenticated}
        saveButton={saveButton}
      />

      {shownCount < rows.length ? (
        <NarrowedSearchHint
          shownCount={shownCount}
          totalCount={rows.length}
          hiddenAddedCount={hiddenAddedCount}
          onClearSearch={() => table.setSearch('')}
        />
      ) : null}

      <MergedListGrid
        table={table}
        rows={rows}
        sharedMode={false}
        highlightedKeys={recentlyAdded?.keys}
        onDeleteRow={handleDeleteRow}
        deleteDisabled={isSharing}
        // Checkbox-based bulk removal: "check rows → Remove Selected".
        selectable={Boolean(onDeleteRows)}
        toolbar={
          <BuilderListToolbar
            list={list}
            rows={rows}
            title={title}
            canShare={canShare}
            curation={curation}
            onDeleteRows={onDeleteRows}
            canUndoRows={canUndoRows}
            onUndoRows={onUndoRows}
            onResetRows={onResetRows}
          />
        }
      />

      <BuilderListFooter
        list={list}
        curation={curation}
        isAuthenticated={isAuthenticated}
        showSaveSection={Boolean(onCreateShare)}
        noteInsert={noteInsert}
        saveButton={saveButton}
        pendingSaveCount={pendingSaveCount}
        onConfirmBulkAction={handleConfirmBulkAction}
      />
    </section>
  );
};
