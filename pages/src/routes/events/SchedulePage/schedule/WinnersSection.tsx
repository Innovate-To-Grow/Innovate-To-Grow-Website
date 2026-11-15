import type {CSSProperties} from 'react';
import type {EventSchedulePayload, ScheduleSection} from '@/features/events/api';
import {scheduleToneClass} from '@/features/events/scheduleTones';
import {grandAwardLabel} from './scheduleModel';

interface WinnersSectionProps {
  data: EventSchedulePayload;
  sections: ScheduleSection[];
}

/** The winners banner: grand awards, then each class's winning tracks. */
export const WinnersSection = ({data, sections}: WinnersSectionProps) => {
  const winnerSections = sections
    .map((section) => ({...section, winnerTracks: section.tracks.filter((track) => track.winner)}))
    .filter((section) => section.winnerTracks.length > 0);
  const grandWinners = data.grand_winners ?? [];

  return (
    <section className="schedule-page-section schedule-page-section-winners" data-embed-section="schedule-winners">
      <div className="schedule-winners-hero">
        <h2 className="itg-section-title schedule-page-section-title schedule-winners-title">
          <span className="schedule-winners-title-emphasis">Winners!</span>{' '}
          <span className="schedule-winners-title-event">{data.event.name}</span>
        </h2>
        {grandWinners.length > 0 && (
          <div className="schedule-grand-winners">
            {grandWinners.map((grandWinner) => (
              <p
                className={`schedule-grand-winner-line is-${grandWinner.section.toLowerCase()}`}
                key={`${grandWinner.section}-${grandWinner.winner}`}
              >
                <span className="schedule-grand-winner-label">{grandAwardLabel(grandWinner.section)}:</span>{' '}
                {grandWinner.winner}
              </p>
            ))}
          </div>
        )}
      </div>
      <div className="schedule-winners">
        {winnerSections.map((section) => (
          <div className="schedule-winners-group" key={section.id}>
            <h3 className="schedule-class-label schedule-winners-group-title">
              {section.label} ({section.code})
            </h3>
            <div
              className="schedule-winners-grid"
              style={{'--winner-column-count': section.winnerTracks.length} as CSSProperties}
            >
              {section.winnerTracks.map((track, index) => (
                <article className={`schedule-winner-card ${scheduleToneClass(section.code, index)}`} key={track.id}>
                  <div className="schedule-winner-card-header">
                    <p className="schedule-winner-track">Track {track.track_number}</p>
                  </div>
                  <div className="schedule-winner-card-body">
                    <p className="schedule-winner-topic">{track.topic}</p>
                    <p className="schedule-winner-name">{track.winner}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
