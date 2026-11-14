import {useCallback, useEffect, useEffectEvent, useRef, type RefObject} from 'react';
import {
  createProjectGridFingerprint,
  createProjectGridItems,
  createProjectGridRowMatcher,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from '../../grid/contracts/projectGrid';
import {subscribeToOtherTabsDraft, type CurationDraft} from './curationDraftStorage';

// New rows are added to the snapshot an Undo/Reset restores, so a save that lands after a Reset is
// neither lost by a later Undo nor allowed to cancel that Undo.
export const appendUnsaved = (snapshot: ProjectGridItem[], added: ProjectGridItem[]) => {
  const inSnapshot = createProjectGridRowMatcher(snapshot);
  return [...snapshot, ...added.filter((row) => !inSnapshot.has(row))];
};

const rowIdentity = (row: ProjectGridRow) => `${row.id ?? ''}\u001f${createProjectGridFingerprint(row)}`;

/**
 * Another tab's rows as items, reusing this tab's item for each project it already shows: the item's key
 * keeps that row's checkbox and Details state.
 */
export const adoptRows = (current: ProjectGridItem[], storedRows: ProjectGridRow[], namespace: string) => {
  const shown = new Map(current.map((item) => [rowIdentity(stripProjectGridItem(item)), item]));
  const fresh = createProjectGridItems(storedRows, namespace);
  return fresh.map((item) => shown.get(rowIdentity(stripProjectGridItem(item))) ?? item);
};

/**
 * The draft is one storage key, written whole by every tab with the builder open. Each tab follows the
 * others' writes, so its next write builds on their changes instead of overwriting them. Returns a check the
 * mirroring effect uses to skip writing back what it just adopted: tabs that serialize the same draft
 * differently would otherwise answer each other's writes forever.
 */
export function useOtherTabsDraft(
  draftMemberRef: RefObject<string | null>,
  adopt: (draft: CurationDraft) => ProjectGridItem[],
) {
  const adoptedRef = useRef<{rows: ProjectGridItem[]; name: string; note: string} | null>(null);
  const handleOtherTabDraft = useEffectEvent((draft: CurationDraft) => {
    adoptedRef.current = {rows: adopt(draft), name: draft.name, note: draft.note};
  });
  useEffect(
    () => subscribeToOtherTabsDraft(() => draftMemberRef.current, (draft) => handleOtherTabDraft(draft)),
    [draftMemberRef],
  );
  return useCallback((rows: ProjectGridItem[], name: string, note: string) => {
    const adopted = adoptedRef.current;
    adoptedRef.current = null;
    return Boolean(adopted && adopted.rows === rows && adopted.name === name && adopted.note === note);
  }, []);
}

interface DraftRowEditsOptions {
  mergedRowsRef: RefObject<ProjectGridItem[]>;
  commitMergedRows: (update: (current: ProjectGridItem[]) => ProjectGridItem[]) => void;
  mergedRowsUndo: ProjectGridItem[] | null;
  setMergedRowsUndo: (rows: ProjectGridItem[] | null) => void;
  onMessage: (message: string) => void;
}

/** Removing rows from the draft (one, the checked ones, or all of them), and undoing the last removal. */
export function useDraftRowEdits({mergedRowsRef, commitMergedRows, mergedRowsUndo, setMergedRowsUndo, onMessage}: DraftRowEditsOptions) {
  const deleteRow = (row: ProjectGridItem) => {
    setMergedRowsUndo(mergedRowsRef.current);
    commitMergedRows((current) => current.filter((item) => item.__key !== row.__key));
    onMessage('Project removed from the curation draft.');
  };

  const deleteRows = (rowsToRemove: ProjectGridItem[]) => {
    if (!rowsToRemove.length) {
      return;
    }
    const removeKeys = new Set(rowsToRemove.map((row) => row.__key));
    setMergedRowsUndo(mergedRowsRef.current);
    commitMergedRows((current) => current.filter((item) => !removeKeys.has(item.__key)));
    onMessage(`${rowsToRemove.length} project${rowsToRemove.length === 1 ? '' : 's'} removed from the curation draft.`);
  };

  const undo = () => {
    if (!mergedRowsUndo) {
      return;
    }
    commitMergedRows(() => mergedRowsUndo);
    setMergedRowsUndo(null);
    onMessage('Curation draft restored.');
  };

  const reset = () => {
    if (!mergedRowsRef.current.length) {
      return;
    }
    setMergedRowsUndo(mergedRowsRef.current);
    commitMergedRows(() => []);
    onMessage('Curation draft cleared. Undo can restore it until you leave this page.');
  };

  return {deleteRow, deleteRows, undo, reset};
}
