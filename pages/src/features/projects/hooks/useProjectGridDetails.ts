import {useCallback, useEffect, useMemo, useSyncExternalStore} from 'react';
import {fetchProjectDetail, type ProjectGridRow} from '@/features/projects/api';

type DetailFields = Pick<ProjectGridRow, 'abstract' | 'student_names'>;
type DetailState =
  | {status: 'idle' | 'loading' | 'error'}
  | {status: 'ready'; details: DetailFields; expiresAt: number};

interface DetailEntry {
  id: string;
  state: DetailState;
  listeners: Set<() => void>;
}

const EMPTY_STATE: DetailState = {status: 'idle'};
const MAX_UNUSED_ENTRIES = 100;
const MAX_CONCURRENT_REQUESTS = 4;
const CACHE_TTL_MS = 5 * 60 * 1000;
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
  while (activeRequests < MAX_CONCURRENT_REQUESTS && pending.length) {
    const entry = pending.shift()!;
    // A row may be collapsed or paged away before its queued request starts.
    if (!entry.listeners.size) {
      publish(entry, EMPTY_STATE);
      pruneCache();
      continue;
    }
    activeRequests += 1;
    void fetchProjectDetail(entry.id)
      .then(({abstract, student_names}) => publish(entry, {
        status: 'ready', details: {abstract, student_names}, expiresAt: Date.now() + CACHE_TTL_MS,
      }))
      .catch(() => publish(entry, {status: 'error'}))
      .finally(() => {
        activeRequests -= 1;
        pruneCache();
        pumpRequests();
      });
  }
}

function requestDetails(entry: DetailEntry) {
  if (entry.state.status === 'loading' || (entry.state.status === 'ready' && entry.state.expiresAt > Date.now())) return;
  publish(entry, {status: 'loading'});
  pending.push(entry);
  pumpRequests();
}

export function useProjectGridDetails(row: ProjectGridRow, loadMissingDetails: boolean) {
  const id = loadMissingDetails && row.id && !row.abstract && !row.student_names ? row.id : null;
  const entry = useMemo(() => id ? getEntry(id) : null, [id]);
  const subscribe = useCallback((listener: () => void) => {
    if (!entry) return () => {};
    entry.listeners.add(listener);
    return () => {
      entry.listeners.delete(listener);
      pruneCache();
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
