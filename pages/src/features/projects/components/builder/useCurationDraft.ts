import {useCallback, useEffect, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {
  createProjectGridItems,
  createProjectGridRowMatcher,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from '../projectGrid';
import {clearPersistedDraft, readPersistedDraft, writePersistedDraft} from './curationDraftStorage';

// New rows are added to the snapshot an Undo/Reset restores, so a save that lands after a Reset is
// neither lost by a later Undo nor allowed to cancel that Undo.
const appendUnsaved = (snapshot: ProjectGridItem[], added: ProjectGridItem[]) => {
  const inSnapshot = createProjectGridRowMatcher(snapshot);
  return [...snapshot, ...added.filter((row) => !inSnapshot.has(row))];
};

/**
 * The curation being built: its merged rows (with a one-step undo), name and note, mirrored to
 * localStorage on every change and dropped when the signed-in member changes.
 */
export function useCurationDraft(onMessage: (message: string) => void) {
  const {isInitializing, unverified, user} = useAuth();
  const memberId = user?.member_uuid ?? null;
  // Seed from the draft kept from an earlier visit (or the login reload).
  const [restoredDraft] = useState(() => readPersistedDraft(memberId));
  const [mergedRows, setMergedRows] = useState<ProjectGridItem[]>(() =>
    createProjectGridItems(restoredDraft.rows, 'restored'),
  );
  const [nameDraft, setNameDraft] = useState(restoredDraft.name);
  const [noteDraft, setNoteDraft] = useState(restoredDraft.note);
  const [mergedRowsUndo, setMergedRowsUndo] = useState<ProjectGridItem[] | null>(null);
  // The rows the latest save added, so the merged table can show and highlight them.
  const [recentlyAdded, setRecentlyAdded] = useState<{keys: ReadonlySet<string>; token: number} | null>(null);
  // The member the draft belongs to (null for a guest's).
  const draftMemberRef = useRef(memberId);
  // Bumped when the draft is dropped for an account change; a save that started before it must not land.
  const accountSequenceRef = useRef(0);
  const mergeSequence = useRef(0);
  // A save resolves after its detail requests, so it must dedup against the merged rows as they are
  // then, not as they were when Save was clicked. Every change goes through commitMergedRows, which
  // keeps this ref equal to the latest list.
  const mergedRowsRef = useRef(mergedRows);
  const commitMergedRows = useCallback((update: (current: ProjectGridItem[]) => ProjectGridItem[]) => {
    const next = update(mergedRowsRef.current);
    mergedRowsRef.current = next;
    setMergedRows(next);
  }, []);

  // Mirror the draft into localStorage on every change so however the visitor leaves (the login reload, a
  // refresh, closing the tab, SPA navigation), it can be restored on return.
  useEffect(() => {
    writePersistedDraft({
      owner: draftMemberRef.current,
      rows: mergedRows.map(stripProjectGridItem),
      name: nameDraft,
      note: noteDraft,
    });
  }, [mergedRows, nameDraft, noteDraft]);

  // Revalidation is not a logout. Keep the draft while identity is being checked, and clear it
  // only when a known member actually logs out or changes accounts. Guest drafts survive login.
  useEffect(() => {
    if (isInitializing || unverified) return;
    if (draftMemberRef.current && draftMemberRef.current !== memberId) {
      accountSequenceRef.current += 1;
      clearPersistedDraft();
      commitMergedRows(() => []);
      setMergedRowsUndo(null);
      setRecentlyAdded(null);
      setNameDraft('');
      setNoteDraft('');
    }
    draftMemberRef.current = memberId;
  }, [commitMergedRows, isInitializing, unverified, memberId]);

  /** Append newly saved rows; they are highlighted and kept in any pending undo snapshot. */
  const appendRows = useCallback(
    (rowsToAppend: ProjectGridRow[]) => {
      mergeSequence.current += 1;
      const added = createProjectGridItems(rowsToAppend, `merged-${mergeSequence.current}`);
      commitMergedRows((current) => [...current, ...added]);
      setMergedRowsUndo((snapshot) => (snapshot ? appendUnsaved(snapshot, added) : null));
      setRecentlyAdded({keys: new Set(added.map((row) => row.__key)), token: mergeSequence.current});
    },
    [commitMergedRows],
  );

  const deleteRow = (row: ProjectGridItem) => {
    setMergedRowsUndo(mergedRowsRef.current);
    commitMergedRows((current) => current.filter((item) => item.__key !== row.__key));
    onMessage('Project removed from merged results.');
  };

  const deleteRows = (rowsToRemove: ProjectGridItem[]) => {
    if (!rowsToRemove.length) {
      return;
    }
    const removeKeys = new Set(rowsToRemove.map((row) => row.__key));
    setMergedRowsUndo(mergedRowsRef.current);
    commitMergedRows((current) => current.filter((item) => !removeKeys.has(item.__key)));
    onMessage(`${rowsToRemove.length} project${rowsToRemove.length === 1 ? '' : 's'} removed from merged results.`);
  };

  const undo = () => {
    if (!mergedRowsUndo) {
      return;
    }
    commitMergedRows(() => mergedRowsUndo);
    setMergedRowsUndo(null);
    onMessage('Merged results restored.');
  };

  const reset = () => {
    if (!mergedRowsRef.current.length) {
      return;
    }
    setMergedRowsUndo(mergedRowsRef.current);
    commitMergedRows(() => []);
    onMessage('Merged results reset. Undo Merged Change can restore them until you leave this page.');
  };

  return {
    mergedRows,
    mergedRowsRef,
    canUndo: Boolean(mergedRowsUndo),
    recentlyAdded,
    nameDraft,
    setNameDraft,
    noteDraft,
    setNoteDraft,
    accountSequenceRef,
    appendRows,
    deleteRow,
    deleteRows,
    undo,
    reset,
  };
}

export type CurationDraftState = ReturnType<typeof useCurationDraft>;
