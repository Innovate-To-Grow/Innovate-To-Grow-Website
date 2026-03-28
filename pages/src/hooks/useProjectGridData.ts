import {useCallback, useEffect, useMemo, useState} from 'react';
import {
  fetchAllPastProjects,
  fetchCurrentProjectsFull,
  fetchPastProjectShare,
  toProjectGridRow,
  type PastProjectShare,
  type ProjectGridRow,
} from '../services/api/projects';

interface ProjectGridDataResult {
  rows: ProjectGridRow[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

interface PastProjectShareResult {
  share: PastProjectShare | null;
  loading: boolean;
  error: string | null;
}

interface ProjectGridRowsState {
  requestKey: symbol | null;
  rows: ProjectGridRow[];
  error: string | null;
}

interface PastProjectShareState {
  requestKey: symbol | null;
  share: PastProjectShare | null;
  error: string | null;
}

export function useCurrentProjectGridData(enabled: boolean = true): ProjectGridDataResult {
  const [refetchCount, setRefetchCount] = useState(0);
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

    fetchCurrentProjectsFull()
      .then((semester) => {
        if (cancelled) return;
        setState({
          requestKey,
          rows: semester.projects.map(toProjectGridRow),
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

  const hasResolved = state.requestKey === requestKey;
  return {
    rows: hasResolved ? state.rows : [],
    loading: !hasResolved,
    error: hasResolved ? state.error : null,
    refetch,
  };
}

export function usePastProjectShareData(shareId: string | undefined): PastProjectShareResult {
  const requestKey = useMemo(() => (shareId ? Symbol(shareId) : null), [shareId]);
  const [state, setState] = useState<PastProjectShareState>({
    requestKey: null,
    share: null,
    error: null,
  });

  useEffect(() => {
    if (!requestKey || !shareId) {
      return;
    }

    let cancelled = false;

    fetchPastProjectShare(shareId)
      .then((result) => {
        if (cancelled) return;
        setState({
          requestKey,
          share: result,
          error: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          requestKey,
          share: null,
          error: err instanceof Error ? err.message : 'Failed to load shared past projects',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [requestKey, shareId]);

  if (!requestKey) {
    return {share: null, loading: false, error: null};
  }

  const hasResolved = state.requestKey === requestKey;
  return {
    share: hasResolved ? state.share : null,
    loading: !hasResolved,
    error: hasResolved ? state.error : null,
  };
}
