import {useCallback, useEffect, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {
  createProjectGridItems,
  createProjectGridRowMatcher,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from '../../../grid/contracts/projectGrid';
import {clearPersistedDraft, readPersistedDraft, writePersistedDraft} from './curationDraftStorage';
import {adoptRows, appendUnsaved, useDraftRowEdits, useOtherTabsDraft} from './curationDraftParts';

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
