import {useCallback, useEffect, useMemo, useSyncExternalStore} from 'react';
import {
  PROJECT_DETAIL_CACHE_TTL_MS,
  PROJECT_DETAIL_CONCURRENCY,
  PROJECT_REQUEST_TIMEOUT_MS,
  fetchProjectDetail,
  needsProjectGridHydration,
  rememberProjectDetail,
  type ProjectGridRow,
} from '@/features/projects/api';

type DetailFields = Pick<ProjectGridRow, 'abstract' | 'student_names'>;
type DetailState =
  | {status: 'idle' | 'loading' | 'error'}
  | {status: 'ready'; details: DetailFields; expiresAt: number};

interface DetailEntry {
  id: string;
  state: DetailState;
  listeners: Set<() => void>;
  /** Aborts the entry's request, set while it is in flight. */
  controller?: AbortController;
}

const EMPTY_STATE: DetailState = {status: 'idle'};
const MAX_UNUSED_ENTRIES = 100;
const cache = new Map<string, DetailEntry>();
const pending: DetailEntry[] = [];
let activeRequests = 0;

// Mounted rows and in-flight requests keep their entry. Only a bounded number of unused results
// survive collapse/pagination; desktop/mobile and other tables share the same entry while mounted.
function pruneCache() {
  const unused = [...cache.values()].filter((entry) => !entry.listeners.size && entry.state.status !== 'loading');
  for (const entry of unused.slice(0, Math.max(0, unused.length - MAX_UNUSED_ENTRIES))) {
    cache.delete(entry.id);
  }
}

function getEntry(id: string) {
  const entry = cache.get(id) ?? {id, state: EMPTY_STATE, listeners: new Set<() => void>()};
  cache.delete(id);
  cache.set(id, entry);
  return entry;
}

function publish(entry: DetailEntry, state: DetailState) {
  entry.state = state;
  entry.listeners.forEach((listener) => listener());
}

function pumpRequests() {
  while (activeRequests < PROJECT_DETAIL_CONCURRENCY && pending.length) {
    const entry = pending.shift()!;
    // A row may be collapsed or paged away before its queued request starts.
    if (!entry.listeners.size) {
      publish(entry, EMPTY_STATE);
      pruneCache();
      continue;
    }
    activeRequests += 1;
    const controller = new AbortController();
    entry.controller = controller;
    // The timeout frees the slot of a request that stalls; otherwise a few of them would hold every slot and leave
    // the rows opened after them "Loading project details…" for good.
    void fetchProjectDetail(entry.id, controller.signal, PROJECT_REQUEST_TIMEOUT_MS)
      .then((detail) => {
        // Saving these rows reuses the details instead of requesting them again.
        rememberProjectDetail(detail);
        publish(entry, {
          status: 'ready',
          details: {abstract: detail.abstract, student_names: detail.student_names},
          expiresAt: Date.now() + PROJECT_DETAIL_CACHE_TTL_MS,
        });
      })
      // A request dropped because no row shows it any more starts over when a row shows it again.
      .catch(() => publish(entry, controller.signal.aborted ? EMPTY_STATE : {status: 'error'}))
      .finally(() => {
        entry.controller = undefined;
        activeRequests -= 1;
        pruneCache();
        pumpRequests();
      });
  }
}

/**
 * Once no row shows an entry, its request is dropped so the slot goes to rows still waiting. Checked after the
 * current task: a row that moves (React's development re-mount, a table re-render) subscribes again first.
 */
function dropRequestIfUnused(entry: DetailEntry) {
  setTimeout(() => {
    if (!entry.listeners.size) entry.controller?.abort();
  }, 0);
}

function requestDetails(entry: DetailEntry) {
  if (entry.state.status === 'loading' || (entry.state.status === 'ready' && entry.state.expiresAt > Date.now())) return;
  publish(entry, {status: 'loading'});
  pending.push(entry);
  pumpRequests();
}

export function useProjectGridDetails(row: ProjectGridRow, loadMissingDetails: boolean) {
  const id = loadMissingDetails && needsProjectGridHydration(row) ? row.id! : null;
  const entry = useMemo(() => id ? getEntry(id) : null, [id]);
  const subscribe = useCallback((listener: () => void) => {
    if (!entry) return () => {};
    entry.listeners.add(listener);
    return () => {
      entry.listeners.delete(listener);
      pruneCache();
      if (!entry.listeners.size) dropRequestIfUnused(entry);
    };
  }, [entry]);
  const getSnapshot = useCallback(() => entry?.state ?? EMPTY_STATE, [entry]);
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    if (entry && (entry.state.status === 'idle' ||
      (entry.state.status === 'ready' && entry.state.expiresAt <= Date.now()))) requestDetails(entry);
  }, [entry]);

  return {
    details: state.status === 'ready' ? state.details : row,
    loading: Boolean(entry) && (state.status === 'idle' || state.status === 'loading'),
    error: state.status === 'error',
    loaded: state.status === 'ready',
    retry: () => { if (entry) requestDetails(entry); },
  };
}
