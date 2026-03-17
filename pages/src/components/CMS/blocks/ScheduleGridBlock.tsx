import {ScheduleGrid} from '../../ScheduleGrid';
import {SCHEDULE_CLASS_CONFIGS} from '../../../config/scheduleConfig';
import {useSheetBlockData} from '../useSheetBlockData';

interface ScheduleGridBlockData {
  heading?: string;
  sheet_source_slug?: string;
}

export const ScheduleGridBlock = ({data}: {data: ScheduleGridBlockData}) => {
  const slug = data.sheet_source_slug || '';
  const {rows, trackInfos, loading, error} = useSheetBlockData(slug);

  return (
    <section className="cms-sheet-block cms-schedule-grid-block">
      {data.heading ? <h2 className="cms-sheet-block-title">{data.heading}</h2> : null}
      <ScheduleGrid
        classes={SCHEDULE_CLASS_CONFIGS}
        rows={rows}
        trackInfos={trackInfos}
        loading={loading}
        error={error}
      />
    </section>
  );
};
