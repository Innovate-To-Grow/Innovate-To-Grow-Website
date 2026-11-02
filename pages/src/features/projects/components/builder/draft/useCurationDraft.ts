import {useCallback, useEffect, useEffectEvent, useRef, useState, type RefObject} from 'react';
import {useAuth} from '@/features/auth';
import {
  createProjectGridFingerprint,
  createProjectGridItems,
  createProjectGridRowMatcher,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from '../../grid/contracts/projectGrid';
import {
  clearPersistedDraft,
  readPersistedDraft,
  subscribeToOtherTabsDraft,
  writePersistedDraft,
  type CurationDraft,
} from './curationDraftStorage';

// New rows are added to the snapshot an Undo/Reset restores, so a save that lands after a Reset is
// neither lost by a later Undo nor allowed to cancel that Undo.
const appendUnsaved = (snapshot: ProjectGridItem[], added: ProjectGridItem[]) => {
  const inSnapshot = createProjectGridRowMatcher(snapshot);
  return [...snapshot, ...added.filter((row) => !inSnapshot.has(row))];
};

const rowIdentity = (row: ProjectGridRow) => `${row.id ?? ''}\u001f${createProjectGridFingerprint(row)}`;

/**
 * Another tab's rows as items, reusing this tab's item for each project it already shows: the item's key
 * keeps that row's checkbox and Details state.
 */
const adoptRows = (current: ProjectGridItem[], storedRows: ProjectGridRow[], namespace: string) => {
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
function useOtherTabsDraft(
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
function useDraftRowEdits({mergedRowsRef, commitMergedRows, mergedRowsUndo, setMergedRowsUndo, onMessage}: DraftRowEditsOptions) {
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

/**
 * The curation being built: its merged rows (with a one-step undo), name and note, mirrored to
 * localStorage on every change (and from other tabs' changes) and dropped when the signed-in member changes.
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
  // Swap in a whole other draft (an account change, another tab's, what a saved curation left). The undo
  // snapshot goes too: undoing would bring back what was swapped out.
  const replaceDraft = useCallback(
    (rows: ProjectGridItem[], name: string, note: string) => {
      commitMergedRows(() => rows);
      setMergedRowsUndo(null);
      setRecentlyAdded(null);
      setNameDraft(name);
      setNoteDraft(note);
    },
    [commitMergedRows],
  );

  const isAdoptedDraft = useOtherTabsDraft(draftMemberRef, (draft) => {
    mergeSequence.current += 1;
    const rows = adoptRows(mergedRowsRef.current, draft.rows, `synced-${mergeSequence.current}`);
    replaceDraft(rows, draft.name, draft.note);
    onMessage('The curation draft was changed in another tab. This page now shows those changes.');
    return rows;
  });

  // Mirror the draft into localStorage on every change so however the visitor leaves (the login reload, a
  // refresh, closing the tab, SPA navigation), it can be restored on return.
  useEffect(() => {
    if (isAdoptedDraft(mergedRows, nameDraft, noteDraft)) return;
    writePersistedDraft({
      owner: draftMemberRef.current,
      rows: mergedRows.map(stripProjectGridItem),
      name: nameDraft,
      note: noteDraft,
    });
  }, [isAdoptedDraft, mergedRows, nameDraft, noteDraft]);

  // Revalidation is not a logout. Keep the draft while identity is being checked, and clear it
  // only when a known member actually logs out or changes accounts. Guest drafts survive login.
  useEffect(() => {
    if (isInitializing || unverified) return;
    if (draftMemberRef.current && draftMemberRef.current !== memberId) {
      accountSequenceRef.current += 1;
      clearPersistedDraft();
      replaceDraft([], '', '');
    }
    draftMemberRef.current = memberId;
  }, [replaceDraft, isInitializing, unverified, memberId]);

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

  const rowEdits = useDraftRowEdits({mergedRowsRef, commitMergedRows, mergedRowsUndo, setMergedRowsUndo, onMessage});

  /**
   * A curation was saved from `sharedRows`: they leave the draft, and so do the name and note that went with
   * them. Rows the save left out (a search hid them) stay for the next curation. Storage is written here and
   * now, because the save opens the new curation, which unmounts this page before the mirroring effect runs.
   */
  const dropShared = (sharedRows: ProjectGridRow[]) => {
    const shared = createProjectGridRowMatcher(sharedRows);
    const remaining = mergedRowsRef.current.filter((row) => !shared.has(row));
    writePersistedDraft({owner: draftMemberRef.current, rows: remaining.map(stripProjectGridItem), name: '', note: ''});
    replaceDraft(remaining, '', '');
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
    ...rowEdits,
    dropShared,
  };
}

export type CurationDraftState = ReturnType<typeof useCurationDraft>;
