import {useState} from 'react';
import {
  fetchPastProjectShare,
  updatePastProjectShare,
  type PastProjectShare,
  type ProjectGridRow,
} from '@/features/projects/api';
import {haveEqualRows, rowsNotYetShared} from './shareRows';
import {
  editPatch,
  isStaleSnapshotConflict,
  type PastProjectSharePatch,
  runnableBaseline,
  SHARE_CONFLICT_RELOAD_FAILED,
  SHARE_CONFLICT_RELOADED,
  SHARE_CONFLICT_RELOADING,
  SHARE_NOT_LOADED,
  useMutationQueueState,
} from './sharedListMutationParts';

/**
 * Edits to a shared list. Every update carries the version it was made from; updates run one at a time,
 * each built from the latest version the previous one returned. When the server reports a newer version
 * (another tab or person), the queue is invalidated, the authoritative version is reloaded and shown, and
 * nothing queued from the stale snapshot is replayed over it.
 */
export function useSharedListMutations(shareId: string | undefined, share: PastProjectShare | null) {
  const [editableShare, setEditableShare] = useState<PastProjectShare | null>(null);
  // Reset the local override to the freshly fetched share whenever `share` changes identity.
  // This is the render-phase equivalent of `useEffect(() => setEditableShare(share), [share])`
  // (https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes):
  // `activeShare` already falls back to `share` when the override is stale, so the rendered output is
  // unchanged, but this avoids the effect's extra cascading commit.
  const [prevShare, setPrevShare] = useState(share);
  if (share !== prevShare) {
    setPrevShare(share);
    setEditableShare(share);
  }
  const activeShare = editableShare?.id === shareId ? editableShare : share;
  const [conflict, setConflict] = useState<{shareId: string; message: string} | null>(null);
  const {mutationQueueRef, mutationEpochRef, mutationShareIdRef, latestShareRef, mutationBlockedRef} =
    useMutationQueueState(shareId, activeShare);

  const reloadAfterConflict = async (targetShareId: string) => {
    // Invalidate every mutation that was queued from the stale snapshot.
    // Those payloads must never be replayed over the newly fetched version.
    mutationEpochRef.current += 1;
    mutationBlockedRef.current = true;
    setConflict({shareId: targetShareId, message: SHARE_CONFLICT_RELOADING});
    try {
      const authoritative = await fetchPastProjectShare(targetShareId);
      if (mutationShareIdRef.current === targetShareId) {
        latestShareRef.current = authoritative;
        mutationBlockedRef.current = false;
        setEditableShare(authoritative);
        setConflict({shareId: targetShareId, message: SHARE_CONFLICT_RELOADED});
      }
    } catch {
      if (mutationShareIdRef.current === targetShareId) {
        setConflict({shareId: targetShareId, message: SHARE_CONFLICT_RELOAD_FAILED});
      }
    }
  };

  const runMutation = async (
    targetShareId: string | undefined,
    queuedEpoch: number,
    buildPatch: (current: PastProjectShare) => PastProjectSharePatch,
  ) => {
    const isCurrentTarget = () =>
      mutationShareIdRef.current === targetShareId && mutationEpochRef.current === queuedEpoch;
    const current = runnableBaseline(
      targetShareId,
      isCurrentTarget() && !mutationBlockedRef.current,
      latestShareRef.current,
    );
    const patch = buildPatch(current);
    if (Object.keys(patch).length === 0) return current;

    try {
      // `current` is the target share (runnableBaseline checked), so its id is the target id.
      const updated = await updatePastProjectShare(current.id, {...patch, version: current.version});
      if (!isCurrentTarget()) {
        throw new Error('The curation changed while this update was running.');
      }
      latestShareRef.current = updated;
      mutationBlockedRef.current = false;
      setEditableShare(updated);
      setConflict(null);
      return updated;
    } catch (mutationError) {
      if (!isStaleSnapshotConflict(mutationError) || mutationShareIdRef.current !== targetShareId) {
        throw mutationError;
      }
      await reloadAfterConflict(current.id);
      throw new Error(SHARE_CONFLICT_RELOADED, {cause: mutationError});
    }
  };

  const enqueueShareMutation = (buildPatch: (current: PastProjectShare) => PastProjectSharePatch) => {
    // Captured at enqueue time: a conflict that bumps the epoch invalidates everything queued before it.
    const targetShareId = shareId;
    const queuedEpoch = mutationEpochRef.current;
    const operation = mutationQueueRef.current.then(() => runMutation(targetShareId, queuedEpoch, buildPatch));
    mutationQueueRef.current = operation.then(
      () => undefined,
      () => undefined,
    );
    return operation;
  };

  /** Save the list as edited from `activeShare`, replayed onto whatever version is current when it runs. */
  const updateShare = async (shareRows: ProjectGridRow[], name: string, note: string) => {
    if (!activeShare) {
      throw new Error(SHARE_NOT_LOADED);
    }
    const baseline = activeShare;
    const rowsChanged = !haveEqualRows(shareRows, baseline.rows);
    await enqueueShareMutation((current) => editPatch(current, baseline, {rows: shareRows, rowsChanged, name, note}));
  };

  /** Append projects; returns how many were new to the (possibly changed) current version. */
  const addShareRows = async (rowsToAdd: ProjectGridRow[]) => {
    if (!activeShare) {
      throw new Error(SHARE_NOT_LOADED);
    }
    // The add loaded project details first, so the share may have changed meanwhile (another tab, a
    // reloaded conflict): append only projects the current version does not already have.
    let appended = 0;
    await enqueueShareMutation((current) => {
      const freshRows = rowsNotYetShared(current.rows, rowsToAdd);
      appended = freshRows.length;
      return freshRows.length ? {rows: [...current.rows, ...freshRows]} : {};
    });
    return appended;
  };

  return {
    activeShare,
    setEditableShare,
    conflictMessage: conflict && conflict.shareId === shareId ? conflict.message : null,
    updateShare,
    addShareRows,
  };
}
