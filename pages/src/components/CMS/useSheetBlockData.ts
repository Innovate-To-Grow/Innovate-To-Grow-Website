import {useLayout} from '../Layout/LayoutProvider/context';
import {useSheetsData} from '../../hooks/useSheetsData';
import type {SheetRow, TrackInfo} from '../../services/api/sheets';

interface UseSheetBlockDataResult {
  rows: SheetRow[];
  trackInfos: TrackInfo[];
  loading: boolean;
  error: string | null;
}

export function useSheetBlockData(slug: string): UseSheetBlockDataResult {
  const normalizedSlug = slug.trim();
  const {sheets_data} = useLayout();
  const prefetched = normalizedSlug ? sheets_data?.[normalizedSlug] : undefined;
  const fetched = useSheetsData({slug: prefetched || !normalizedSlug ? '' : normalizedSlug});

  return {
    rows: prefetched?.rows ?? fetched.rows,
    trackInfos: prefetched?.track_infos ?? fetched.trackInfos,
    loading: prefetched ? false : fetched.loading,
    error: prefetched ? null : fetched.error,
  };
}
