import type {CSSProperties} from 'react';
import type {ScheduleSection, ScheduleSlot} from '@/features/events/api';
import {scheduleToneClass} from '@/features/events/scheduleTones';
import {presentationGrid, type PresentationGrid} from './scheduleModel';

type OnTeamClick = (searchValue: string) => void;

interface SlotContentProps {
  slot: ScheduleSlot | undefined;
  isFullyEmpty: boolean;
  /** `schedule-mobile` or `schedule-presentation`: the two layouts style the same parts. */
  classPrefix: string;
  onTeamClick: OnTeamClick;
}

/** A slot: its team (a button that searches the projects list) and organization, or a Break. */
const SlotContent = ({slot, isFullyEmpty, classPrefix, onTeamClick}: SlotContentProps) => {
  if (!slot) {
    return isFullyEmpty ? <span className={`${classPrefix}-break`}>Break</span> : null;
  }
  if (slot.is_break) {
    return <span className={`${classPrefix}-break`}>Break</span>;
  }
  return (
    <>
      <button
        type="button"
        className={`${classPrefix}-team`}
        onClick={() => onTeamClick(slot.team_number || slot.display_text)}
      >
        {slot.display_text}
      </button>
      {slot.organization ? <span className={`${classPrefix}-org`}>{slot.organization}</span> : null}
    </>
  );
};

const slotAt = (track: PresentationGrid['tracks'][number], order: number) =>
  track.slots.find((entry) => entry.order === order);

const MobileTrackCards = ({section, grid, onTeamClick}: {section: ScheduleSection; grid: PresentationGrid; onTeamClick: OnTeamClick}) => (
  <div className="schedule-page-mobile-grid">
    {grid.tracks.map((track, columnIndex) => (
      <article
        key={`${section.id}-${track.id}-mobile`}
        className={`schedule-mobile-card ${scheduleToneClass(section.code, columnIndex)}`}
      >
        <header className="schedule-mobile-card-header">
          <div>
            <p className="schedule-mobile-track-label">Track {track.track_number}</p>
            <h4 className="schedule-mobile-topic">{track.topic || track.label || 'Presentation Track'}</h4>
          </div>
          <p className="schedule-mobile-room">{track.room || 'TBD'}</p>
        </header>

        <div className="schedule-mobile-slots">
          {grid.times.map((time, rowIndex) => {
            const order = rowIndex + 1;
            const slot = slotAt(track, order);
            const isFullyEmpty = grid.fullyEmptyOrders.has(order);
            return (
              <div key={`${track.id}-${order}-mobile`} className="schedule-mobile-slot">
                <div className="schedule-mobile-time">{time}</div>
                <div className={`schedule-mobile-slot-content ${slot?.is_break || isFullyEmpty ? 'is-break' : ''}`}>
                  <SlotContent slot={slot} isFullyEmpty={isFullyEmpty} classPrefix="schedule-mobile" onTeamClick={onTeamClick} />
                </div>
              </div>
            );
          })}
        </div>
      </article>
    ))}
  </div>
);

const PresentationTableHead = ({section, grid}: {section: ScheduleSection; grid: PresentationGrid}) => (
  <thead>
    <tr>
      <th className="schedule-presentation-corner">Room:</th>
      {grid.tracks.map((track) => (
        <th key={track.id} className="schedule-presentation-room">
          {track.room || 'TBD'}
        </th>
      ))}
    </tr>
    <tr>
      <th className="schedule-presentation-corner">
        <span className="sr-only">Track</span>
      </th>
      {grid.tracks.map((track) => (
        <th key={`${track.id}-label`} className="schedule-presentation-track">
          Track {track.track_number}
        </th>
      ))}
    </tr>
    {grid.showTopicRow && (
      <tr>
        <th className="schedule-presentation-corner">
          <span className="sr-only">Topic</span>
        </th>
        {grid.tracks.map((track, index) => (
          <td key={`${track.id}-topic`} className={`schedule-presentation-topic-cell ${scheduleToneClass(section.code, index)}`}>
            <span className="schedule-presentation-topic">{track.topic || 'TBD'}</span>
          </td>
        ))}
      </tr>
    )}
  </thead>
);

const PresentationTable = ({section, grid, onTeamClick}: {section: ScheduleSection; grid: PresentationGrid; onTeamClick: OnTeamClick}) => (
  <div className="schedule-page-table-wrap">
    {/* The track count sizes the table's minimum width in the events sheet, so the grid
        fits the main column and only scrolls when a class has too many tracks to fit. */}
    <table
      className={`schedule-presentation-table schedule-presentation-table--${section.code.toLowerCase()}`}
      style={{'--schedule-track-count': grid.tracks.length} as CSSProperties}
    >
      {/* Narrow time column; the fixed layout shares the rest equally between tracks. */}
      <colgroup>
        <col className="schedule-presentation-time-col" />
        {grid.tracks.map((track) => (
          <col key={`${track.id}-col`} />
        ))}
      </colgroup>
      <PresentationTableHead section={section} grid={grid} />
      <tbody>
        {grid.times.map((time, rowIndex) => {
          const order = rowIndex + 1;
          const isFullyEmpty = grid.fullyEmptyOrders.has(order);
          return (
            <tr key={`${section.id}-${order}`}>
              <th scope="row" className="schedule-presentation-time">{time}</th>
              {grid.tracks.map((track, columnIndex) => {
                const slot = slotAt(track, order);
                return (
                  <td
                    key={`${track.id}-${order}`}
                    className={`schedule-presentation-slot ${scheduleToneClass(section.code, columnIndex)}${
                      slot?.is_break || isFullyEmpty ? ' schedule-presentation-slot-break' : ''
                    }`}
                    title={slot?.tooltip || ''}
                  >
                    <SlotContent slot={slot} isFullyEmpty={isFullyEmpty} classPrefix="schedule-presentation" onTeamClick={onTeamClick} />
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

interface PresentationSectionProps {
  section: ScheduleSection;
  isMobileLayout: boolean;
  onTeamClick: OnTeamClick;
}

/** One class's presentations: cards per track on phones, a time-by-track table otherwise. */
export const PresentationSection = ({section, isMobileLayout, onTeamClick}: PresentationSectionProps) => {
  const grid = presentationGrid(section);
  return (
    <section className="schedule-presentation-block">
      <h3 className="schedule-class-label schedule-presentation-heading">
        {section.label} ({section.code})
      </h3>
      {isMobileLayout ? (
        <MobileTrackCards section={section} grid={grid} onTeamClick={onTeamClick} />
      ) : (
        <PresentationTable section={section} grid={grid} onTeamClick={onTeamClick} />
      )}
    </section>
  );
};
