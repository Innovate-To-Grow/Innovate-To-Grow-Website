import {useMemo} from 'react';
import type {SheetRow, TrackInfo} from '../SheetsDataTable';
import './ScheduleGrid.css';

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
  /** Accent color for this class section */
  accentColor?: string;
}

interface ScheduleGridProps {
  classes: ClassConfig[];
  rows: SheetRow[];
  trackInfos: TrackInfo[];
  loading?: boolean;
  error?: string | null;
  onTeamClick?: (teamNum: string) => void;
}

function addMinutes(time: string, minutes: number): string {
  let [h, m] = time.split(':').map(Number);
  m += minutes;
  while (m >= 60) {
    h += 1;
    m -= 60;
  }
  if (h > 12) h -= 12;
  return `${h}:${m < 10 ? '0' + m : m}`;
}

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

  if (loading) return <div className="sg-loading">Loading schedule...</div>;
  if (error) return <div className="sg-error">{error}</div>;

  return (
    <div className="sg-container">
      {classes.map((cls, classIndex) => {
        const startOffset = classOffsets[classIndex] ?? 0;
        const accent = cls.accentColor || '#002856';
        const times: string[] = [];
        let t = cls.startTime;
        for (let i = 0; i < cls.orderCount; i++) {
          times.push(t);
          t = addMinutes(t, cls.slotMinutes);
        }

        return (
          <div key={cls.code} className="sg-class-section">
            <h3 className="sg-class-title" style={{color: accent}}>
              {cls.label} ({cls.code})
            </h3>
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th className="sg-th sg-th-time">Room:</th>
                    {Array.from({length: cls.trackCount}, (_, ti) => {
                      const info = trackInfos[startOffset + ti];
                      return (
                        <th key={ti} className="sg-th sg-th-room">
                          {info?.room || ''}
                        </th>
                      );
                    })}
                  </tr>
                  <tr>
                    <th className="sg-th sg-th-time" />
                    {cls.trackLabels.map((label, ti) => (
                      <th key={ti} className="sg-th sg-th-track" style={{color: accent}}>
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {times.map((time, orderIdx) => {
                    const order = orderIdx + 1;
                    return (
                      <tr key={order}>
                        <th className="sg-td-time">{time}</th>
                        {Array.from({length: cls.trackCount}, (_, ti) => {
                          const track = startOffset + ti + 1;
                          const cell = cellMap[cls.code]?.[`${order}-${track}`];
                          return (
                            <td key={ti} className="sg-td-cell" title={cell?.NameTitle || ''}>
                              {cell ? (
                                <>
                                  <button
                                    className="sg-team-btn"
                                    style={{color: accent}}
                                    onClick={() => onTeamClick?.(cell['Team#'].substring(0, 3))}
                                  >
                                    {cell['Team#']}
                                  </button>
                                  <span className="sg-org">{cell.Organization}</span>
                                </>
                              ) : null}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
};
