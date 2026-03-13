import {useState, useEffect} from 'react';
import {fetchSheetsData} from '../services/api/sheets';
import type {SheetRow, TrackInfo} from '../services/api/sheets';

interface UseSheetsDataOptions {
  slug: string;
}

interface UseSheetsDataResult {
  rows: SheetRow[];
  trackInfos: TrackInfo[];
  loading: boolean;
  error: string | null;
}

interface SheetsDataState {
  slug: string;
  rows: SheetRow[];
  trackInfos: TrackInfo[];
  error: string | null;
}

export function useSheetsData({slug}: UseSheetsDataOptions): UseSheetsDataResult {
  const [state, setState] = useState<SheetsDataState>({
    slug: '',
    rows: [],
    trackInfos: [],
    error: null,
  });

  useEffect(() => {
    if (!slug) {
      return;
    }

    let cancelled = false;

    fetchSheetsData(slug)
      .then((data) => {
        if (cancelled) return;
        setState({
          slug,
          rows: data.rows,
          trackInfos: data.track_infos,
          error: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          slug,
          rows: [],
          trackInfos: [],
          error: err instanceof Error ? err.message : 'Failed to load data',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (!slug) {
    return {rows: [], trackInfos: [], loading: false, error: null};
  }

  if (state.slug !== slug) {
    return {rows: [], trackInfos: [], loading: true, error: null};
  }

  return {
    rows: state.rows,
    trackInfos: state.trackInfos,
    loading: false,
    error: state.error,
  };
}
