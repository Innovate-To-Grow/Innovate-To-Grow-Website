import {useEffect, useRef, useState} from 'react';
import {
  DEFAULT_PAST_PROJECT_SHARE_NAME,
  fetchPastProjectShare,
  updatePastProjectShare,
  type PastProjectShare,
  type ProjectGridRow,
} from '@/features/projects/api';
import {haveEqualRows, rebaseSubmittedRows, rowsNotYetShared} from './shareRows';

type PastProjectSharePatch = Partial<Pick<PastProjectShare, 'name' | 'rows' | 'note'>>;

export const shareDisplayTitle = (share: Pick<PastProjectShare, 'name'>) =>
  share.name?.trim() || DEFAULT_PAST_PROJECT_SHARE_NAME;

const SHARE_CONFLICT_RELOADED =
  'This shared page changed elsewhere. The latest version was reloaded; review it before editing again.';
const SHARE_CONFLICT_RELOADING =
  'This shared page changed elsewhere. Reloading the latest version before any more edits are applied.';
const SHARE_CONFLICT_RELOAD_FAILED =
  'This shared page changed elsewhere, and the latest version could not be reloaded. Reload the page before editing again.';
const SHARE_NOT_LOADED = 'Shared past projects are not loaded yet.';

/** The server's 409 for an update sent with an outdated `version`. */
const isStaleSnapshotConflict = (error: unknown) => {
  if (!error || typeof error !== 'object') return false;
  const response = (error as {response?: unknown}).response;
  if (!response || typeof response !== 'object') return false;
  const {status, data} = response as {status?: unknown; data?: unknown};
  return status === 409 && Boolean(data && typeof data === 'object' && (data as {code?: unknown}).code === 'stale_snapshot');
};

/**
 * The share this mutation builds on: the latest known version of its target. Throws when the target is no
 * longer current (another share, a conflict since it was queued, a reload pending) or not loaded yet.
 */
const runnableBaseline = (
  targetShareId: string | undefined,
  targetIsCurrent: boolean,
  latest: PastProjectShare | null,
): PastProjectShare => {
  if (!targetShareId || !targetIsCurrent) {
    throw new Error(SHARE_CONFLICT_RELOAD_FAILED);
  }
  if (!latest || latest.id !== targetShareId) {
    throw new Error(SHARE_NOT_LOADED);
  }
  return latest;
};

interface ShareEdit {
  rows: ProjectGridRow[];
  rowsChanged: boolean;
  name: string;
  note: string;
}

/** An edit made from ``baseline``, replayed onto ``current``: only what the edit changed, rows rebased. */
const editPatch = (current: PastProjectShare, baseline: PastProjectShare, edit: ShareEdit): PastProjectSharePatch => {
  const patch: PastProjectSharePatch = {};
  if (edit.rowsChanged) {
    const rebasedRows = rebaseSubmittedRows(current.rows, baseline.rows, edit.rows);
    if (!haveEqualRows(rebasedRows, current.rows)) {
      patch.rows = rebasedRows;
    }
  }
  // MergedResultsTable passes back the title it displays, which for a legacy blank-name share is
  // the fallback, so compare against that rather than the raw name or a note/row edit would store
  // the fallback as a typed name.
  if (edit.name !== shareDisplayTitle(baseline)) patch.name = edit.name;
  if (edit.note !== baseline.note) patch.note = edit.note;
  return patch;
};

/**
 * The mutation queue's bookkeeping: the queue, its epoch, which share it serves, the latest version seen
 * and whether a conflict reload blocks it. Switching to another share starts all of it afresh; a newer
 * version of the active share becomes the latest.
 */
function useMutationQueueState(shareId: string | undefined, activeShare: PastProjectShare | null) {
  const mutationQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const mutationEpochRef = useRef(0);
  const mutationShareIdRef = useRef(shareId);
  const latestShareRef = useRef<PastProjectShare | null>(activeShare);
  const mutationBlockedRef = useRef(false);

  useEffect(() => {
    if (mutationShareIdRef.current !== shareId) {
      mutationShareIdRef.current = shareId;
      mutationEpochRef.current += 1;
      mutationQueueRef.current = Promise.resolve();
      latestShareRef.current = null;
      mutationBlockedRef.current = false;
    }
    if (
      activeShare &&
      (latestShareRef.current?.id !== activeShare.id || activeShare.version >= latestShareRef.current.version)
    ) {
      latestShareRef.current = activeShare;
    }
  }, [activeShare, shareId]);

  return {mutationQueueRef, mutationEpochRef, mutationShareIdRef, latestShareRef, mutationBlockedRef};
}

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
        throw new Error('The shared page changed while this update was running.');
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
