import {useCallback, useEffect, useMemo, useState} from 'react';
import {
  fetchAllPastProjects,
  scheduleProjectToGridRow,
  toProjectGridRow,
  type ProjectGridRow,
} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';

interface ProjectGridDataResult {
  rows: ProjectGridRow[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

interface ProjectGridRowsState {
  requestKey: symbol | null;
  rows: ProjectGridRow[];
  error: string | null;
}

export function useCurrentProjectGridData(enabled: boolean = true): ProjectGridDataResult {
  const [refetchCount, setRefetchCount] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- refetchCount forces a new Symbol to trigger the fetch useEffect
  const requestKey = useMemo(() => (enabled ? Symbol('current-project-grid') : null), [enabled, refetchCount]);
  const [state, setState] = useState<ProjectGridRowsState>({
    requestKey: null,
    rows: [],
    error: null,
  });

  const refetch = useCallback(() => setRefetchCount((c) => c + 1), []);

  useEffect(() => {
    if (!requestKey) {
      return;
    }

    let cancelled = false;

    fetchCurrentSchedule()
      .then((payload) => {
        if (cancelled) return;
        setState({
          requestKey,
          rows: payload.projects.map(scheduleProjectToGridRow),
          error: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          requestKey,
          rows: [],
          error: err instanceof Error ? err.message : 'Failed to load current projects',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [requestKey]);

  if (!requestKey) {
    return {rows: [], loading: false, error: null, refetch};
  }

  const hasResolved = state.requestKey === requestKey;
  return {
    rows: hasResolved ? state.rows : [],
    loading: !hasResolved,
    error: hasResolved ? state.error : null,
    refetch,
  };
}

export function usePastProjectGridData(enabled: boolean = true): ProjectGridDataResult {
  const [refetchCount, setRefetchCount] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- refetchCount forces a new Symbol to trigger the fetch useEffect
  const requestKey = useMemo(() => (enabled ? Symbol('past-project-grid') : null), [enabled, refetchCount]);
  const [state, setState] = useState<ProjectGridRowsState>({
    requestKey: null,
    rows: [],
    error: null,
  });

  const refetch = useCallback(() => setRefetchCount((c) => c + 1), []);

  useEffect(() => {
    if (!requestKey) {
      return;
    }

    let cancelled = false;

    fetchAllPastProjects()
      .then((projects) => {
        if (cancelled) return;
        setState({
          requestKey,
          rows: projects.map(toProjectGridRow),
          error: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          requestKey,
          rows: [],
          error: err instanceof Error ? err.message : 'Failed to load past projects',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [requestKey]);

  if (!requestKey) {
    return {rows: [], loading: false, error: null, refetch};
  }

  // Stale-while-revalidate: a refetch() keeps serving the previously resolved rows (loading stays
  // false) until the new response lands, so consumers keep their search tables mounted — and their
  // per-table curation intact — across a refresh. Only the very first load reports loading.
  const hasResolved = state.requestKey === requestKey;
  const hasEverResolved = state.requestKey !== null;
  return {
    rows: state.rows,
    loading: !hasResolved && !hasEverResolved,
    error: hasResolved ? state.error : null,
    refetch,
  };
}
