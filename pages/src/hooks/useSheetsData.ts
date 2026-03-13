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

export function useSheetsData({slug}: UseSheetsDataOptions): UseSheetsDataResult {
  const [rows, setRows] = useState<SheetRow[]>([]);
  const [trackInfos, setTrackInfos] = useState<TrackInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) {
      setRows([]);
      setTrackInfos([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchSheetsData(slug)
      .then((data) => {
        if (cancelled) return;
        setRows(data.rows);
        setTrackInfos(data.track_infos);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load data');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  return {rows, trackInfos, loading, error};
}
