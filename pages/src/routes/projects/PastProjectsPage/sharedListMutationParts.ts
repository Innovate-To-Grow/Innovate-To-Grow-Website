import {useEffect, useRef} from 'react';
import {type PastProjectShare, type ProjectGridRow} from '@/features/projects/api';
import {curationBranding} from '@/features/projects/components/curation/merged/note/curationBranding';
import {haveEqualRows, rebaseSubmittedRows} from './shareRows';

export type PastProjectSharePatch = Partial<Pick<PastProjectShare, 'name' | 'rows' | 'note'>>;

/** A share's name, or for one stored with a blank name the default the server gives its rows. */
export const shareDisplayTitle = (share: Pick<PastProjectShare, 'name' | 'rows'>) =>
  share.name?.trim() || curationBranding(share.rows ?? []).defaultName;

export const SHARE_CONFLICT_RELOADED =
  'This curation changed elsewhere. The latest version was reloaded; review it before editing again.';
export const SHARE_CONFLICT_RELOADING =
  'This curation changed elsewhere. Reloading the latest version before any more edits are applied.';
export const SHARE_CONFLICT_RELOAD_FAILED =
  'This curation changed elsewhere, and the latest version could not be reloaded. Reload the page before editing again.';
export const SHARE_NOT_LOADED = 'This curation is not loaded yet.';

/** The server's 409 for an update sent with an outdated `version`. */
export const isStaleSnapshotConflict = (error: unknown) => {
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
export const runnableBaseline = (
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
export const editPatch = (current: PastProjectShare, baseline: PastProjectShare, edit: ShareEdit): PastProjectSharePatch => {
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
export function useMutationQueueState(shareId: string | undefined, activeShare: PastProjectShare | null) {
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
