import {useMemo} from 'react';
import {useAuth} from '@/features/auth';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import type {ProjectGridItem, ProjectGridRow} from '../../grid/contracts/projectGrid';
import {signInToSave} from '../list/curationNote';
import {CurationSaveButton} from './CurationSaveSection';
import {useCurationShare, type PastProjectShareCreationResult} from './useCurationShare';
import {useMergedList, useRevealRecentlyAdded, type ListMessage} from '../list/useMergedList';
import {useNoteInsertFields} from '../list/useNoteInsertFields';

export interface BuilderMergedListProps {
  id?: string;
  className?: string;
  rows: ProjectGridItem[];
  recentlyAdded: {keys: ReadonlySet<string>; token: number} | null;
  pendingSaveCount: number;
  title: string;
  /** The page's latest report about the draft (a removal, an undo, another tab's change), for the status line. */
  message?: ListMessage | null;
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

type BuilderListOptions = Pick<
  BuilderMergedListProps,
  | 'rows'
  | 'recentlyAdded'
  | 'pendingSaveCount'
  | 'message'
  | 'onCreateShare'
  | 'nameDraft'
  | 'noteDraft'
  | 'onNameDraftChange'
  | 'onNoteDraftChange'
  | 'onDeleteRow'
  | 'onResetRows'
>;

/** The list's table, the curation save, and the row actions, which all wait while a curation is saved. */
export function useBuilderList({
  rows,
  recentlyAdded,
  pendingSaveCount,
  message,
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
  const list = useMergedList(rows, message);
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
    list.rememberRemoval(row);
    onDeleteRow(row);
  };

  const handleConfirmBulkAction = () => {
    if (list.pendingBulkAction === 'reset-builder' && !isSharing) {
      onResetRows?.();
    }
    list.setPendingBulkAction(null);
  };

  const saveButton = canShare ? (
    <CurationSaveButton
      hasRows={visibleRows.length > 0}
      isSharing={isSharing}
      pendingSaveCount={pendingSaveCount}
      onSave={() => void curation.createShare()}
    />
  ) : null;
  // The whole draft, not just the rows its search shows, goes along to the full page from the widget.
  const {path} = useProjectCatalog();
  const signIn = useMemo(() => signInToSave(rows, path), [path, rows]);

  return {
    isAuthenticated,
    canShare,
    list,
    noteInsert,
    hiddenAddedCount,
    curation,
    saveButton,
    signIn,
    handleDeleteRow,
    handleConfirmBulkAction,
  };
}
