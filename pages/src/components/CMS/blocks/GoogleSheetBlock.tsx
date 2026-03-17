import {ScheduleGrid} from '../../ScheduleGrid';
import {SheetsDataTable} from '../../SheetsDataTable';
import {SCHEDULE_CLASS_CONFIGS} from '../../../config/scheduleConfig';
import {useSheetBlockData} from '../useSheetBlockData';

interface GoogleSheetBlockData {
  heading?: string;
  sheet_source_slug?: string;
  sheet_view_slug?: string;
  display_mode?: string;
}

export const GoogleSheetBlock = ({data}: {data: GoogleSheetBlockData}) => {
  const slug = data.sheet_source_slug || '';
  const displayMode = (data.display_mode || 'table').toLowerCase();
  const {rows, trackInfos, loading, error} = useSheetBlockData(slug);
  const sectionId = data.sheet_view_slug || undefined;

  return (
    <section className="cms-sheet-block cms-google-sheet-block" id={sectionId}>
      {data.heading ? <h2 className="cms-sheet-block-title">{data.heading}</h2> : null}
      {displayMode === 'schedule' || displayMode === 'schedule_grid' || displayMode === 'schedule-grid' ? (
        <ScheduleGrid
          classes={SCHEDULE_CLASS_CONFIGS}
          rows={rows}
          trackInfos={trackInfos}
          loading={loading}
          error={error}
        />
      ) : (
        <SheetsDataTable rows={rows} loading={loading} error={error} />
      )}
    </section>
  );
};
