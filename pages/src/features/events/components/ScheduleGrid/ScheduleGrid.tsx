import {useMemo} from 'react';
import type {SheetRow, TrackInfo} from '@/components/SheetsDataTable';
import {addMinutes} from '@/lib/format';
import {scheduleToneClass} from '@/features/events/scheduleTones';

export interface ClassConfig {
  /** Class code, e.g. "CAP", "CEE", "CSE" */
  code: string;
  /** Display name */
  label: string;
  /** Number of tracks for this class */
  trackCount: number;
  /** Number of time slots (order rows) */
  orderCount: number;
  /** Start time e.g. "1:00" */
  startTime: string;
  /** Minutes per slot */
  slotMinutes: number;
  /** Track labels e.g. ["FoodTech", "Precision"] */
  trackLabels: string[];
}

interface ScheduleGridProps {
  classes: ClassConfig[];
  rows: SheetRow[];
  trackInfos: TrackInfo[];
  loading?: boolean;
  error?: string | null;
  onTeamClick?: (teamNum: string) => void;
}

/** The start time of each of the class's slots. */
const slotTimes = (cls: ClassConfig): string[] => {
  const times: string[] = [];
  let t = cls.startTime;
  for (let i = 0; i < cls.orderCount; i++) {
    times.push(t);
    t = addMinutes(t, cls.slotMinutes);
  }
  return times;
};

const ScheduleCell = ({cell, toneClass, onTeamClick}: {
  cell: SheetRow | undefined;
  toneClass: string;
  onTeamClick?: (teamNum: string) => void;
}) => (
  <td className={`sg-td-cell ${toneClass}`} title={cell?.NameTitle || ''}>
    {cell ? (
      <>
        <button
          type="button"
          className="sg-team-btn"
          onClick={() => onTeamClick?.(cell['Team#'].substring(0, 3))}
        >
          {cell['Team#']}
        </button>
        <span className="sg-org">{cell.Organization}</span>
      </>
    ) : null}
  </td>
);

interface ScheduleClassSectionProps {
  cls: ClassConfig;
  /** Index of the class's first track among all tracks (``trackInfos`` and the sheet's Track numbers). */
  startOffset: number;
  trackInfos: TrackInfo[];
  /** The class's rows by `${order}-${track}`. */
  cells: Record<string, SheetRow> | undefined;
  onTeamClick?: (teamNum: string) => void;
}

/** One class: its rooms and tracks across the top, a row per time slot. */
const ScheduleClassSection = ({cls, startOffset, trackInfos, cells, onTeamClick}: ScheduleClassSectionProps) => (
  <section className="sg-class-section">
    <h3 className="sg-class-title">
      {cls.label} ({cls.code})
    </h3>
    <div className="sg-table-wrap">
      <table className="sg-table">
        <thead>
          <tr>
            <th className="sg-th sg-th-time">Room:</th>
            {Array.from({length: cls.trackCount}, (_, ti) => (
              <th key={ti} className="sg-th sg-th-room">
                {trackInfos[startOffset + ti]?.room || ''}
              </th>
            ))}
          </tr>
          <tr>
            <th className="sg-th sg-th-time">
              <span className="sr-only">Track</span>
            </th>
            {cls.trackLabels.map((label, ti) => (
              <th key={ti} className={`sg-th sg-th-track ${scheduleToneClass(cls.code, ti)}`}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slotTimes(cls).map((time, orderIdx) => {
            const order = orderIdx + 1;
            return (
              <tr key={order}>
                <th className="sg-td-time">{time}</th>
                {Array.from({length: cls.trackCount}, (_, ti) => (
                  <ScheduleCell
                    key={ti}
                    cell={cells?.[`${order}-${startOffset + ti + 1}`]}
                    toneClass={scheduleToneClass(cls.code, ti)}
                    onTeamClick={onTeamClick}
                  />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  </section>
);

export const ScheduleGrid = ({
  classes,
  rows,
  trackInfos,
  loading,
  error,
  onTeamClick,
}: ScheduleGridProps) => {
  // Build a lookup: class -> { `${order}-${track}`: SheetRow }
  const cellMap = useMemo(() => {
    const map: Record<string, Record<string, SheetRow>> = {};
    for (const row of rows) {
      if (!row.Track || !row.Order) continue;
      const key = `${row.Order}-${row.Track}`;
      if (!map[row.Class]) map[row.Class] = {};
      map[row.Class][key] = row;
    }
    return map;
  }, [rows]);

  const classOffsets = useMemo(() => {
    const offsets: number[] = [];
    let nextOffset = 0;

    for (const cls of classes) {
      offsets.push(nextOffset);
      nextOffset += cls.trackCount;
    }

    return offsets;
  }, [classes]);

  if (loading) return <div className="sg-loading" role="status">Loading schedule...</div>;
  if (error) return <div className="sg-error" role="alert">{error}</div>;

  return (
    <div className="sg-container">
      {classes.map((cls, classIndex) => (
        <ScheduleClassSection
          key={cls.code}
          cls={cls}
          startOffset={classOffsets[classIndex] ?? 0}
          trackInfos={trackInfos}
          cells={cellMap[cls.code]}
          onTeamClick={onTeamClick}
        />
      ))}
    </div>
  );
};
